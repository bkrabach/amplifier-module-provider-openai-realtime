"""Basic conversation example using OpenAI Realtime provider.

This example demonstrates a simple voice conversation without tool calling.
"""

import asyncio
import os
from pathlib import Path

from amplifier_core import AmplifierSession


async def main():
    """Run basic voice conversation."""

    # Configuration
    config = {
        "session": {"orchestrator": "loop-streaming", "context": "context-simple"},
        "providers": [
            {
                "module": "provider-openai-realtime",
                "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
                "config": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "gpt-4o-realtime-preview-2024-12-17",
                    "voice": "alloy",
                    "temperature": 0.7,
                },
            }
        ],
    }

    # Load sample audio (PCM16, 24kHz, mono)
    # You would typically get this from microphone capture
    audio_file = Path("sample_audio.pcm")
    if not audio_file.exists():
        print("Error: sample_audio.pcm not found")
        print("Create a PCM16 audio file at 24kHz sample rate")
        return

    audio_bytes = audio_file.read_bytes()

    # Create session and send audio
    async with AmplifierSession(config=config) as session:
        print("Sending audio to OpenAI Realtime API...")

        response = await session.execute(
            {
                "role": "user",
                "content": [{"type": "audio", "data": audio_bytes, "format": "pcm16", "sample_rate": 24000}],
            }
        )

        # Extract results
        audio_output = response.raw["audio_data"]
        transcript = response.raw["transcript"]

        # Save audio output
        output_file = Path("response_audio.pcm")
        output_file.write_bytes(audio_output)

        print(f"\nTranscript: {transcript}")
        print(f"Audio saved to: {output_file}")
        print(f"Tokens used - Input: {response.usage['input']}, Output: {response.usage['output']}")


if __name__ == "__main__":
    asyncio.run(main())
