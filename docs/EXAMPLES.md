# Examples

This document provides usage recipes and troubleshooting examples for the OpenAI Realtime provider.

## Basic Usage

### Example 1: Simple Voice Echo

```python
from amplifier_core import AmplifierSession
import pyaudio
import wave

# Configuration
config = {
    "session": {
        "orchestrator": "loop-basic",
        "context": "context-simple"
    },
    "providers": [{
        "module": "provider-openai-realtime",
        "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
        "config": {
            "api_key": "${OPENAI_API_KEY}",
            "model": "gpt-4o-realtime-preview-2024-12-17",
            "voice": "alloy"
        }
    }]
}

def record_audio(duration: float = 3.0) -> bytes:
    """Record audio from microphone."""
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=24000,
        input=True,
        frames_per_buffer=1024
    )

    print(f"Recording for {duration} seconds...")
    frames = []
    for _ in range(0, int(24000 / 1024 * duration)):
        data = stream.read(1024)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    p.terminate()

    return b''.join(frames)

def play_audio(audio_bytes: bytes):
    """Play audio through speakers."""
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=24000,
        output=True
    )

    stream.write(audio_bytes)
    stream.stop_stream()
    stream.close()
    p.terminate()

async def main():
    """Simple voice conversation."""
    async with AmplifierSession(config=config) as session:
        # Record user speech
        audio_input = record_audio(duration=3.0)

        # Send to provider
        response = await session.execute({
            "role": "user",
            "content": [{"type": "audio", "data": audio_input}]
        })

        # Get audio response
        audio_output = response.raw["audio_data"]
        transcript = response.raw["transcript"]

        print(f"Assistant: {transcript}")

        # Play response
        play_audio(audio_output)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Example 2: Voice Conversation Loop

```python
async def conversation_loop():
    """Multi-turn voice conversation."""
    config = {
        "session": {
            "orchestrator": "loop-basic",
            "context": "context-simple"
        },
        "providers": [{
            "module": "provider-openai-realtime",
            "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
            "config": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": "alloy"
            }
        }]
    }

    async with AmplifierSession(config=config) as session:
        print("Voice assistant ready. Press Enter to speak, 'q' to quit.")

        while True:
            # Wait for user
            command = input("\nPress Enter to speak (or 'q' to quit): ")
            if command.lower() == 'q':
                break

            # Record user speech
            print("Listening...")
            audio_input = record_audio(duration=5.0)

            # Send and get response
            response = await session.execute({
                "role": "user",
                "content": [{"type": "audio", "data": audio_input}]
            })

            # Display and play
            transcript = response.raw["transcript"]
            print(f"Assistant: {transcript}")

            audio_output = response.raw["audio_data"]
            play_audio(audio_output)

if __name__ == "__main__":
    import asyncio
    asyncio.run(conversation_loop())
```

### Example 3: Text + Audio Mixed

```python
async def mixed_conversation():
    """Mix text and audio in same session."""
    config = {
        "session": {
            "orchestrator": "loop-basic",
            "context": "context-simple"
        },
        "providers": [{
            "module": "provider-openai-realtime",
            "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
            "config": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": "alloy"
            }
        }]
    }

    async with AmplifierSession(config=config) as session:
        # Turn 1: Text input
        response1 = await session.execute({
            "role": "user",
            "content": [{"type": "text", "text": "Hello, who are you?"}]
        })
        print(f"Text response: {response1.content}")

        # Turn 2: Audio input
        audio_input = record_audio()
        response2 = await session.execute({
            "role": "user",
            "content": [{"type": "audio", "data": audio_input}]
        })

        # Get audio response
        audio_output = response2.raw["audio_data"]
        transcript = response2.raw["transcript"]
        print(f"Audio response: {transcript}")
        play_audio(audio_output)

if __name__ == "__main__":
    import asyncio
    asyncio.run(mixed_conversation())
```

## Tool Integration

### Example 4: Voice File Assistant

```python
async def voice_file_assistant():
    """Voice assistant with filesystem access."""
    config = {
        "session": {
            "orchestrator": "loop-basic",
            "context": "context-simple"
        },
        "providers": [{
            "module": "provider-openai-realtime",
            "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
            "config": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": "alloy"
            }
        }],
        "tools": [{
            "module": "tool-filesystem",
            "source": "git+https://github.com/microsoft/amplifier-module-tool-filesystem@main",
            "config": {
                "base_path": "./documents"
            }
        }]
    }

    async with AmplifierSession(config=config) as session:
        # User asks about files
        print("Say: 'What files do I have?'")
        audio_input = record_audio(duration=3.0)

        response = await session.execute({
            "role": "user",
            "content": [{"type": "audio", "data": audio_input}]
        })

        # Assistant calls filesystem tool and responds
        transcript = response.raw["transcript"]
        print(f"Assistant: {transcript}")

        audio_output = response.raw["audio_data"]
        play_audio(audio_output)

if __name__ == "__main__":
    import asyncio
    asyncio.run(voice_file_assistant())
```

### Example 5: Weather Assistant

```python
async def weather_assistant():
    """Voice weather assistant with API calls."""
    config = {
        "session": {
            "orchestrator": "loop-basic",
            "context": "context-simple"
        },
        "providers": [{
            "module": "provider-openai-realtime",
            "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
            "config": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": "alloy",
                "temperature": 0.7
            }
        }],
        "tools": [{
            "module": "tool-web",
            "source": "git+https://github.com/microsoft/amplifier-module-tool-web@main"
        }]
    }

    async with AmplifierSession(config=config) as session:
        while True:
            print("\nAsk about weather (or 'q' to quit):")
            command = input("Press Enter to speak: ")
            if command.lower() == 'q':
                break

            audio_input = record_audio(duration=5.0)

            response = await session.execute({
                "role": "user",
                "content": [{"type": "audio", "data": audio_input}]
            })

            transcript = response.raw["transcript"]
            print(f"Assistant: {transcript}")

            audio_output = response.raw["audio_data"]
            play_audio(audio_output)

if __name__ == "__main__":
    import asyncio
    asyncio.run(weather_assistant())
```

## File Handling

### Example 6: Working with WAV Files

```python
import wave
from pathlib import Path

def load_audio_file(filepath: str) -> bytes:
    """Load audio from WAV file."""
    with wave.open(filepath, 'rb') as wav:
        if wav.getnchannels() != 1:
            raise ValueError("Only mono audio supported")
        if wav.getsampwidth() != 2:
            raise ValueError("Only 16-bit audio supported")
        if wav.getframerate() != 24000:
            raise ValueError("Only 24kHz sample rate supported")

        return wav.readframes(wav.getnframes())

def save_audio_file(audio_bytes: bytes, filepath: str):
    """Save audio to WAV file."""
    with wave.open(filepath, 'wb') as wav:
        wav.setnchannels(1)      # Mono
        wav.setsampwidth(2)      # 16-bit
        wav.setframerate(24000)  # 24kHz
        wav.writeframes(audio_bytes)

async def process_audio_file():
    """Process audio from file."""
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [{
            "module": "provider-openai-realtime",
            "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
            "config": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": "alloy"
            }
        }]
    }

    async with AmplifierSession(config=config) as session:
        # Load audio from file
        audio_input = load_audio_file("input.wav")

        # Process
        response = await session.execute({
            "role": "user",
            "content": [{"type": "audio", "data": audio_input}]
        })

        # Save response
        audio_output = response.raw["audio_data"]
        save_audio_file(audio_output, "output.wav")

        print(f"Transcript: {response.raw['transcript']}")
        print("Response saved to output.wav")

if __name__ == "__main__":
    import asyncio
    asyncio.run(process_audio_file())
```

## Advanced Patterns

### Example 7: Voice + Screen Context

```python
async def voice_with_screen_context():
    """Combine voice input with screen context."""
    config = {
        "session": {
            "orchestrator": "loop-basic",
            "context": "context-simple"
        },
        "providers": [{
            "module": "provider-openai-realtime",
            "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
            "config": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": "alloy"
            }
        }]
    }

    async with AmplifierSession(config=config) as session:
        # First, provide text context
        await session.execute({
            "role": "user",
            "content": [{
                "type": "text",
                "text": "I'm looking at a document about Python decorators."
            }]
        })

        # Then ask via voice
        print("Now ask a question about the document...")
        audio_input = record_audio()

        response = await session.execute({
            "role": "user",
            "content": [{"type": "audio", "data": audio_input}]
        })

        # Model remembers text context
        audio_output = response.raw["audio_data"]
        transcript = response.raw["transcript"]
        print(f"Assistant: {transcript}")
        play_audio(audio_output)

if __name__ == "__main__":
    import asyncio
    asyncio.run(voice_with_screen_context())
```

### Example 8: Batch Processing

```python
from pathlib import Path

async def batch_process_audio_files():
    """Process multiple audio files."""
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [{
            "module": "provider-openai-realtime",
            "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
            "config": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": "alloy"
            }
        }]
    }

    input_dir = Path("audio_inputs")
    output_dir = Path("audio_outputs")
    output_dir.mkdir(exist_ok=True)

    async with AmplifierSession(config=config) as session:
        for input_file in input_dir.glob("*.wav"):
            print(f"Processing {input_file.name}...")

            # Load audio
            audio_input = load_audio_file(str(input_file))

            # Process
            response = await session.execute({
                "role": "user",
                "content": [{"type": "audio", "data": audio_input}]
            })

            # Save output
            audio_output = response.raw["audio_data"]
            output_file = output_dir / f"response_{input_file.name}"
            save_audio_file(audio_output, str(output_file))

            # Log transcript
            print(f"  → {response.raw['transcript']}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(batch_process_audio_files())
```

### Example 9: Error Handling

```python
from amplifier_module_provider_openai_realtime.exceptions import (
    WebSocketConnectionError,
    AudioFormatError,
    SessionInitializationError
)

async def robust_conversation():
    """Voice conversation with comprehensive error handling."""
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [{
            "module": "provider-openai-realtime",
            "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
            "config": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": "alloy"
            }
        }]
    }

    max_retries = 3

    for attempt in range(max_retries):
        try:
            async with AmplifierSession(config=config) as session:
                while True:
                    try:
                        # Record audio
                        print("\nListening...")
                        audio_input = record_audio(duration=5.0)

                        # Validate audio format
                        if len(audio_input) % 2 != 0:
                            raise AudioFormatError("Invalid audio data")

                        # Send to provider
                        response = await session.execute({
                            "role": "user",
                            "content": [{"type": "audio", "data": audio_input}]
                        })

                        # Play response
                        audio_output = response.raw["audio_data"]
                        transcript = response.raw["transcript"]
                        print(f"Assistant: {transcript}")
                        play_audio(audio_output)

                    except AudioFormatError as e:
                        print(f"Audio format error: {e}")
                        print("Please try again.")
                        continue

                    except KeyboardInterrupt:
                        print("\nGoodbye!")
                        break

        except WebSocketConnectionError as e:
            print(f"Connection error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print("Retrying in 2 seconds...")
                await asyncio.sleep(2)
                continue
            else:
                print("Max retries reached. Exiting.")
                break

        except SessionInitializationError as e:
            print(f"Session initialization failed: {e}")
            print("Check your configuration and API key.")
            break

        except Exception as e:
            print(f"Unexpected error: {e}")
            break

if __name__ == "__main__":
    import asyncio
    asyncio.run(robust_conversation())
```

## Troubleshooting Recipes

### Recipe 1: Testing Connection

```python
async def test_connection():
    """Test if OpenAI Realtime API is accessible."""
    import websockets

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return

    model = "gpt-4o-realtime-preview-2024-12-17"
    url = f"wss://api.openai.com/v1/realtime?model={model}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    try:
        async with websockets.connect(url, extra_headers=headers) as ws:
            print("✅ Connection successful")

            # Test session update
            await ws.send(json.dumps({
                "type": "session.update",
                "session": {"voice": "alloy"}
            }))

            response = await ws.recv()
            print(f"✅ Session initialized: {json.loads(response)['type']}")

    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_connection())
```

### Recipe 2: Audio Format Validation

```python
def validate_audio(audio_bytes: bytes) -> dict:
    """Validate audio format for provider."""
    issues = []

    # Check type
    if not isinstance(audio_bytes, bytes):
        issues.append(f"Wrong type: {type(audio_bytes)}, expected bytes")

    # Check length
    if len(audio_bytes) == 0:
        issues.append("Empty audio data")
    elif len(audio_bytes) % 2 != 0:
        issues.append(f"Odd byte length: {len(audio_bytes)} (must be even for PCM16)")

    # Calculate duration
    duration = len(audio_bytes) / (2 * 24000)  # 2 bytes/sample, 24kHz

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "size_bytes": len(audio_bytes),
        "duration_seconds": duration,
        "sample_count": len(audio_bytes) // 2
    }

# Usage
audio = record_audio()
validation = validate_audio(audio)
if not validation["valid"]:
    print("Audio validation failed:")
    for issue in validation["issues"]:
        print(f"  - {issue}")
else:
    print(f"✅ Valid audio: {validation['duration_seconds']:.2f}s")
```

### Recipe 3: Monitoring Token Usage

```python
async def monitor_token_usage():
    """Track token usage across conversation."""
    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [{
            "module": "provider-openai-realtime",
            "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
            "config": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": "alloy"
            }
        }]
    }

    total_input_tokens = 0
    total_output_tokens = 0

    async with AmplifierSession(config=config) as session:
        for turn in range(3):
            print(f"\n--- Turn {turn + 1} ---")

            audio_input = record_audio()
            response = await session.execute({
                "role": "user",
                "content": [{"type": "audio", "data": audio_input}]
            })

            # Track usage
            input_tokens = response.usage.get("input", 0)
            output_tokens = response.usage.get("output", 0)
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens

            print(f"Input tokens: {input_tokens}")
            print(f"Output tokens: {output_tokens}")
            print(f"Transcript: {response.raw['transcript']}")

            audio_output = response.raw["audio_data"]
            play_audio(audio_output)

        print(f"\n--- Total Usage ---")
        print(f"Total input tokens: {total_input_tokens}")
        print(f"Total output tokens: {total_output_tokens}")
        print(f"Total tokens: {total_input_tokens + total_output_tokens}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(monitor_token_usage())
```

### Recipe 4: Debugging WebSocket Messages

```python
import logging

async def debug_websocket_messages():
    """Log all WebSocket messages for debugging."""

    # Enable debug logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("amplifier_module_provider_openai_realtime")

    config = {
        "session": {"orchestrator": "loop-basic", "context": "context-simple"},
        "providers": [{
            "module": "provider-openai-realtime",
            "source": "git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main",
            "config": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": "alloy"
            }
        }]
    }

    async with AmplifierSession(config=config) as session:
        audio_input = record_audio()

        response = await session.execute({
            "role": "user",
            "content": [{"type": "audio", "data": audio_input}]
        })

        # Check logs for WebSocket message details
        print(f"Response: {response.raw['transcript']}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(debug_websocket_messages())
```

## Common Issues

### Issue 1: "Connection failed" Error

**Symptoms**: Cannot establish WebSocket connection

**Diagnosis**:
```python
# Check API key
api_key = os.getenv("OPENAI_API_KEY")
print(f"API key set: {bool(api_key)}")
if api_key:
    print(f"Key starts with: {api_key[:10]}...")

# Check network
import socket
try:
    socket.create_connection(("api.openai.com", 443), timeout=5)
    print("✅ Network OK")
except Exception as e:
    print(f"❌ Network issue: {e}")
```

**Solutions**:
- Verify `OPENAI_API_KEY` environment variable
- Check firewall allows WSS (port 443)
- Test with `curl https://api.openai.com`

### Issue 2: Audio Sounds Garbled

**Symptoms**: Output audio is distorted or noisy

**Diagnosis**:
```python
# Check audio format
import numpy as np

audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
print(f"Sample range: {audio_array.min()} to {audio_array.max()}")
print(f"Mean: {audio_array.mean()}")
print(f"Std dev: {audio_array.std()}")

# Look for clipping
clipped_samples = np.sum(np.abs(audio_array) > 32000)
print(f"Clipped samples: {clipped_samples}")
```

**Solutions**:
- Ensure audio is PCM16, 24kHz, mono
- Check for clipping (normalize if needed)
- Verify microphone settings

### Issue 3: Model Not Responding

**Symptoms**: Request succeeds but no audio returned

**Diagnosis**:
```python
# Check response structure
print(f"Response keys: {response.raw.keys()}")
print(f"Audio data length: {len(response.raw.get('audio_data', b''))}")
print(f"Transcript: {response.raw.get('transcript', 'MISSING')}")

# Check WebSocket response
ws_response = response.raw.get("websocket_response", {})
print(f"Response type: {ws_response.get('type')}")
```

**Solutions**:
- Check if audio input is silent (model may respond to silence with silence)
- Verify system instructions are not too restrictive
- Try with known good audio sample

## See Also

- [Architecture](ARCHITECTURE.md) - Module design
- [API Contract](API_CONTRACT.md) - Provider protocol
- [Audio Format](AUDIO_FORMAT.md) - Audio specifications
- [Session Lifecycle](SESSION_LIFECYCLE.md) - WebSocket management
- [Function Calling](FUNCTION_CALLING.md) - Tool integration
