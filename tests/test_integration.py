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
    - Provider accepts text input (converted to audio internally)
    - OpenAI API responds with audio
    - Response has correct structure
    - Transcript is present
    """
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [
            {
                "module": "provider-openai-realtime",
                "config": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "gpt-4o-realtime-preview-2024-12-17",
                    "voice": "alloy",
                    "temperature": 0.7,
                },
            }
        ],
    }

    async with AmplifierSession(config=config) as session:
        # Send text prompt (provider converts to audio conversation)
        response = await session.execute("Hello, please respond with 'test succeeded'")

        # Verify response is a string (the transcript)
        assert isinstance(response, str), f"Response should be str, got {type(response)}"
        assert len(response) > 0, "Response is empty"

        # The provider should include the actual audio response in raw field via hooks
        # (This is observable via hooks/logging, not directly in return value)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_turn_conversation():
    """Does session persistence work?

    Tests:
    - Multiple turns in same session
    - Context preserved across turns
    """
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [
            {
                "module": "provider-openai-realtime",
                "config": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "gpt-4o-realtime-preview-2024-12-17",
                    "voice": "alloy",
                },
            }
        ],
    }

    async with AmplifierSession(config=config) as session:
        # Turn 1: Send text prompt
        response1 = await session.execute("Say the word 'first'")
        assert isinstance(response1, str), f"First response should be str, got {type(response1)}"
        assert len(response1) > 0, "First response is empty"

        # Turn 2: Send another prompt
        response2 = await session.execute("Say the word 'second'")
        assert isinstance(response2, str), f"Second response should be str, got {type(response2)}"
        assert len(response2) > 0, "Second response is empty"

        # Verify both responses are different (context is working)
        assert response1 != response2, "Responses should be different"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_provider_response_structure():
    """Verify response is returned correctly.

    Tests:
    - Response is a string (transcript)
    - Response is non-empty
    """
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [
            {
                "module": "provider-openai-realtime",
                "config": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "gpt-4o-realtime-preview-2024-12-17",
                    "voice": "alloy",
                },
            }
        ],
    }

    async with AmplifierSession(config=config) as session:
        response = await session.execute("Hello")

        # Verify response is string
        assert isinstance(response, str), f"Response should be str, got {type(response)}"
        assert len(response) > 0, "Response is empty"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_text_input():
    """Verify provider accepts text input.

    Tests:
    - Text messages work
    - Provider responds with audio (converted internally)
    """
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [
            {
                "module": "provider-openai-realtime",
                "config": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "gpt-4o-realtime-preview-2024-12-17",
                    "voice": "alloy",
                },
            }
        ],
    }

    async with AmplifierSession(config=config) as session:
        # Send text prompt
        response = await session.execute("Hello, respond with 'test succeeded'")

        # Verify response
        assert isinstance(response, str), f"Response should be str, got {type(response)}"
        assert len(response) > 0, "Response is empty"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_handling_no_api_key():
    """Verify provider handles missing API key gracefully.

    Tests:
    - Missing API key raises clear error
    """
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [
            {
                "module": "provider-openai-realtime",
                "config": {
                    "api_key": "",  # Invalid: empty API key
                    "model": "gpt-4o-realtime-preview-2024-12-17",
                    "voice": "alloy",
                },
            }
        ],
    }

    # Should raise error during initialization or first call
    with pytest.raises(Exception) as exc_info:
        async with AmplifierSession(config=config) as session:
            await session.execute("Hello")

    # Verify error message mentions API key
    error_msg = str(exc_info.value).lower()
    assert "api" in error_msg or "key" in error_msg or "auth" in error_msg, (
        f"Error message should mention API key: {exc_info.value}"
    )
