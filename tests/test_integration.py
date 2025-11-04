"""
Integration tests for OpenAI Realtime provider.

These tests make REAL OpenAI API calls and require OPENAI_API_KEY.
They validate the complete end-to-end provider behavior.
"""

import os

import numpy as np
import pytest
from amplifier_core import AmplifierSession

# Skip all integration tests if no API key
pytestmark = pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="Requires OPENAI_API_KEY environment variable")


def generate_test_audio(duration_seconds: float = 1.0, sample_rate: int = 24000) -> bytes:
    """Generate simple test audio (silence or tone).

    Args:
        duration_seconds: Audio duration
        sample_rate: Sample rate in Hz

    Returns:
        PCM16 audio bytes
    """
    num_samples = int(duration_seconds * sample_rate)
    # Generate silence (all zeros)
    audio_array = np.zeros(num_samples, dtype=np.int16)
    return audio_array.tobytes()


def generate_tone_audio(frequency: float = 440.0, duration_seconds: float = 1.0, sample_rate: int = 24000) -> bytes:
    """Generate simple sine wave tone.

    Args:
        frequency: Tone frequency in Hz
        duration_seconds: Audio duration
        sample_rate: Sample rate in Hz

    Returns:
        PCM16 audio bytes
    """
    num_samples = int(duration_seconds * sample_rate)
    t = np.linspace(0, duration_seconds, num_samples, endpoint=False)
    audio_array = (np.sin(2 * np.pi * frequency * t) * 32767 * 0.5).astype(np.int16)
    return audio_array.tobytes()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_basic_audio_roundtrip():
    """THE test that matters - does it work with real OpenAI?

    Tests:
    - Provider accepts audio input
    - OpenAI API responds with audio
    - Response has correct structure
    - Transcript is present
    """
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [
            {
                "module": "provider-openai-realtime",
                "source": "git+https://github.com/microsoft/amplifier-module-provider-openai-realtime@main",
                "config": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "gpt-4o-realtime-preview-2024-12-17",
                    "voice": "alloy",
                    "temperature": 0.7,
                },
            }
        ],
    }

    # Generate test audio (1 second tone)
    test_audio = generate_tone_audio(duration_seconds=1.0)

    async with AmplifierSession(config=config) as session:
        # Send audio input
        response = await session.execute(
            {
                "role": "user",
                "content": [{"type": "audio", "data": test_audio, "format": "pcm16", "sample_rate": 24000}],
            }
        )

        # Verify response structure
        assert response is not None, "No response received"
        assert hasattr(response, "raw"), "Response missing 'raw' field"

        # Verify raw field has required audio data
        raw = response.raw
        assert "audio_data" in raw, "Missing audio_data in response.raw"
        assert "audio_format" in raw, "Missing audio_format in response.raw"
        assert "sample_rate" in raw, "Missing sample_rate in response.raw"
        assert "transcript" in raw, "Missing transcript in response.raw"
        assert "session_id" in raw, "Missing session_id in response.raw"

        # Verify audio data is valid
        audio_data = raw["audio_data"]
        assert isinstance(audio_data, bytes), f"audio_data not bytes: {type(audio_data)}"
        assert len(audio_data) > 0, "audio_data is empty"
        assert len(audio_data) % 2 == 0, f"audio_data odd length: {len(audio_data)}"

        # Verify format
        assert raw["audio_format"] == "pcm16", f"Wrong audio_format: {raw['audio_format']}"
        assert raw["sample_rate"] == 24000, f"Wrong sample_rate: {raw['sample_rate']}"

        # Verify transcript exists
        transcript = raw["transcript"]
        assert isinstance(transcript, str), f"transcript not str: {type(transcript)}"
        assert len(transcript) > 0, "transcript is empty"

        # Verify content field matches transcript
        assert response.content == transcript, "content doesn't match transcript"

        # Verify usage exists
        assert hasattr(response, "usage"), "Response missing 'usage' field"
        assert "input" in response.usage, "Missing input tokens in usage"
        assert "output" in response.usage, "Missing output tokens in usage"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_turn_conversation():
    """Does session persistence work?

    Tests:
    - Multiple turns in same session
    - Session ID persists
    - Context preserved across turns
    """
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [
            {
                "module": "provider-openai-realtime",
                "source": "git+https://github.com/microsoft/amplifier-module-provider-openai-realtime@main",
                "config": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "gpt-4o-realtime-preview-2024-12-17",
                    "voice": "alloy",
                },
            }
        ],
    }

    async with AmplifierSession(config=config) as session:
        # Turn 1: Send audio
        audio1 = generate_tone_audio(duration_seconds=0.5)
        response1 = await session.execute(
            {"role": "user", "content": [{"type": "audio", "data": audio1, "format": "pcm16", "sample_rate": 24000}]}
        )

        session_id1 = response1.raw["session_id"]
        assert session_id1, "No session_id in first response"

        # Turn 2: Send another audio
        audio2 = generate_tone_audio(duration_seconds=0.5, frequency=880.0)
        response2 = await session.execute(
            {"role": "user", "content": [{"type": "audio", "data": audio2, "format": "pcm16", "sample_rate": 24000}]}
        )

        session_id2 = response2.raw["session_id"]
        assert session_id2, "No session_id in second response"

        # Verify session ID persists
        assert session_id1 == session_id2, f"Session ID changed between turns: {session_id1} != {session_id2}"

        # Verify both responses have valid audio
        assert len(response1.raw["audio_data"]) > 0, "First response has no audio"
        assert len(response2.raw["audio_data"]) > 0, "Second response has no audio"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_provider_response_structure():
    """Verify ProviderResponse matches contract.

    Tests:
    - Response has all required fields per API_CONTRACT.md
    - Field types are correct
    - Content blocks present
    """
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [
            {
                "module": "provider-openai-realtime",
                "source": "git+https://github.com/microsoft/amplifier-module-provider-openai-realtime@main",
                "config": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "gpt-4o-realtime-preview-2024-12-17",
                    "voice": "alloy",
                },
            }
        ],
    }

    test_audio = generate_tone_audio(duration_seconds=1.0)

    async with AmplifierSession(config=config) as session:
        response = await session.execute(
            {
                "role": "user",
                "content": [{"type": "audio", "data": test_audio, "format": "pcm16", "sample_rate": 24000}],
            }
        )

        # Verify top-level fields
        assert hasattr(response, "content"), "Missing 'content' field"
        assert hasattr(response, "raw"), "Missing 'raw' field"
        assert hasattr(response, "usage"), "Missing 'usage' field"
        assert hasattr(response, "content_blocks"), "Missing 'content_blocks' field"

        # content should be str
        assert isinstance(response.content, str), f"content should be str, got {type(response.content)}"

        # raw should be dict with specific keys
        assert isinstance(response.raw, dict), f"raw should be dict, got {type(response.raw)}"

        required_raw_keys = [
            "audio_data",
            "audio_format",
            "sample_rate",
            "transcript",
            "session_id",
            "websocket_response",
        ]
        for key in required_raw_keys:
            assert key in response.raw, f"Missing required key in raw: {key}"

        # Verify raw field types
        assert isinstance(response.raw["audio_data"], bytes), "audio_data not bytes"
        assert isinstance(response.raw["audio_format"], str), "audio_format not str"
        assert isinstance(response.raw["sample_rate"], int), "sample_rate not int"
        assert isinstance(response.raw["transcript"], str), "transcript not str"
        assert isinstance(response.raw["session_id"], str), "session_id not str"
        assert isinstance(response.raw["websocket_response"], dict), "websocket_response not dict"

        # usage should be dict with input/output
        assert isinstance(response.usage, dict), f"usage should be dict, got {type(response.usage)}"
        assert "input" in response.usage, "Missing 'input' in usage"
        assert "output" in response.usage, "Missing 'output' in usage"
        assert isinstance(response.usage["input"], int), "input tokens not int"
        assert isinstance(response.usage["output"], int), "output tokens not int"

        # content_blocks should be list with TextBlock
        assert isinstance(response.content_blocks, list), (
            f"content_blocks should be list, got {type(response.content_blocks)}"
        )
        assert len(response.content_blocks) > 0, "content_blocks is empty"

        # First block should have text field
        first_block = response.content_blocks[0]
        assert hasattr(first_block, "text"), "First content block missing 'text' field"
        assert first_block.text == response.content, "First block text doesn't match response.content"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_text_input():
    """Verify provider accepts text input.

    Tests:
    - Text messages work alongside audio
    - System messages converted to instructions
    """
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [
            {
                "module": "provider-openai-realtime",
                "source": "git+https://github.com/microsoft/amplifier-module-provider-openai-realtime@main",
                "config": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "gpt-4o-realtime-preview-2024-12-17",
                    "voice": "alloy",
                },
            }
        ],
    }

    async with AmplifierSession(config=config) as session:
        # Send text input
        response = await session.execute(
            {"role": "user", "content": [{"type": "text", "text": "Hello, respond with 'test succeeded'"}]}
        )

        # Verify response
        assert response is not None, "No response for text input"
        assert hasattr(response, "raw"), "Response missing 'raw' field"
        assert "transcript" in response.raw, "Missing transcript"

        # Should still have audio (provider converts text to audio response)
        assert "audio_data" in response.raw, "Missing audio_data"
        assert len(response.raw["audio_data"]) > 0, "audio_data is empty"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_handling_invalid_audio():
    """Verify provider handles invalid audio gracefully.

    Tests:
    - Invalid audio format raises AudioFormatError
    - Error has clear message
    """
    from amplifier_module_provider_openai_realtime.exceptions import AudioFormatError

    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [
            {
                "module": "provider-openai-realtime",
                "source": "git+https://github.com/microsoft/amplifier-module-provider-openai-realtime@main",
                "config": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "gpt-4o-realtime-preview-2024-12-17",
                    "voice": "alloy",
                },
            }
        ],
    }

    async with AmplifierSession(config=config) as session:
        # Send invalid audio (odd byte length)
        with pytest.raises((AudioFormatError, ValueError, Exception)) as exc_info:
            await session.execute(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "audio",
                            "data": b"odd",  # Invalid: odd length
                            "format": "pcm16",
                            "sample_rate": 24000,
                        }
                    ],
                }
            )

        # Verify error message is informative
        error_msg = str(exc_info.value).lower()
        assert "audio" in error_msg or "invalid" in error_msg or "pcm16" in error_msg, (
            f"Error message not informative: {exc_info.value}"
        )
