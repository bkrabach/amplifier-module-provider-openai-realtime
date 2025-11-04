"""Voice conversation with tool calling example.

This example demonstrates how to use the OpenAI Realtime provider with
Amplifier's tool system for function calling.
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

from amplifier_core import AmplifierSession


async def main():
    """Run voice conversation with tool calling."""

    # Configuration with tools
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
        "tools": [
            {
                "module": "tool-filesystem",
                "source": "git+https://github.com/microsoft/amplifier-module-tool-filesystem@main",
            }
        ],
    }

    # Load sample audio asking for file information
    # Example: "What files are in my documents folder?"
    audio_file = Path("sample_audio_with_question.pcm")
    if not audio_file.exists():
        print("Error: sample_audio_with_question.pcm not found")
        print("Record audio asking a question that needs tool calling")
        print('Example: "What is the current time?"')
        return

    audio_bytes = audio_file.read_bytes()

    # Create session
    async with AmplifierSession(config=config) as session:
        print("Sending audio with tool calling enabled...")

        # Turn 1: Audio input that triggers tool call
        response = await session.execute(
            {
                "role": "user",
                "content": [{"type": "audio", "data": audio_bytes, "format": "pcm16", "sample_rate": 24000}],
            }
        )

        # Check if tools were called
        if response.tool_calls:
            print(f"\nTools called: {[tc.tool for tc in response.tool_calls]}")

        # Extract audio response
        audio_output = response.raw["audio_data"]
        transcript = response.raw["transcript"]

        # Save results
        output_file = Path(f"response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pcm")
        output_file.write_bytes(audio_output)

        print(f"\nTranscript: {transcript}")
        print(f"Audio saved to: {output_file}")
        print(f"Tokens - Input: {response.usage['input']}, Output: {response.usage['output']}")

        # Turn 2: Follow-up question
        print("\n--- Turn 2 ---")
        followup_audio = Path("followup_audio.pcm")
        if followup_audio.exists():
            response2 = await session.execute(
                {
                    "role": "user",
                    "content": [
                        {"type": "audio", "data": followup_audio.read_bytes(), "format": "pcm16", "sample_rate": 24000}
                    ],
                }
            )

            print(f"Followup transcript: {response2.raw['transcript']}")


if __name__ == "__main__":
    asyncio.run(main())
