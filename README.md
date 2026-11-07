# amplifier-module-provider-openai-realtime

OpenAI Realtime API provider module for Amplifier - native speech-to-speech interactions.

## Overview

This provider module integrates OpenAI's Realtime API with Amplifier, enabling native speech-to-speech conversations without the traditional STT/LLM/TTS pipeline. The Realtime API processes audio directly for ultra-low latency voice interactions with full function calling support.

## Features

- **Native audio I/O**: Direct audio streaming to/from OpenAI via WebSocket
- **Turn-based conversation**: Clean request/response audio interaction
- **Function calling**: Full support for Amplifier's tool system
- **Voice selection**: Five voices (`alloy`, `echo`, `shimmer`, `marin`, `cedar`)
- **Session management**: Persistent WebSocket connection with automatic instruction conversion
- **Zero kernel changes**: Pure edge implementation, no existing module modifications

## Quick Start

```bash
# Set your OpenAI API key
export OPENAI_API_KEY="sk-..."

# Install the provider
uv pip install git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main

# Use in your application
python your_voice_app.py
```

See [examples/](examples/) for complete working examples.

## Installation

### From Git

```bash
# Install latest
uv pip install git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@main

# Install specific version/branch
uv pip install git+https://github.com/robotdad/amplifier-module-provider-openai-realtime@v0.1.0
```

### Local Development

```bash
# Clone the repository
git clone https://github.com/robotdad/amplifier-module-provider-openai-realtime
cd amplifier-module-provider-openai-realtime

# Install in editable mode with dev dependencies
uv sync --dev

# Run tests
uv run pytest
```

## Configuration

### Basic Usage

The provider follows Amplifier's standard provider configuration pattern:

```python
from amplifier_core import AmplifierSession

config = {
    "session": {
        "orchestrator": "loop-streaming",
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
    }]
}

async with AmplifierSession(config=config) as session:
    # Send audio, receive audio response
    response = await session.execute({
        "role": "user",
        "content": [{"type": "audio", "data": audio_bytes}]
    })

    # Access audio from raw field
    audio_output = response.raw["audio_data"]
    transcript = response.content  # Text transcript
```

### Compatibility boundary and model selection

The receiver accepts documented `response.output_audio.*` and
`response.output_audio_transcript.*` events as well as legacy `response.audio.*`
and `response.audio_transcript.*` events. Each base64 delta is decoded separately,
then PCM bytes are assembled in output/content order. Only matching
`response.done` completes a turn; audio/transcript done events do not.

Offline serialized-transcript tests exercise `complete()` through the real
session manager and WebSocket adapter. They cover text/PCM input, session update
confirmation, padded chunks, transcript/usage/tool output, adjacent turns,
duplicate event IDs, unrelated response IDs, errors and cancellation. A cancelled
or failed receive closes the connection before a subsequent turn can reuse it.
Unknown event types do not fabricate audio. Conflicting duplicate events,
malformed audio and unsuccessful terminal responses raise errors rather than
report success. Legacy full-audio done payloads remain a fallback only when no
deltas were received. The single-turn adapter does not multiplex responses.

This is **receive-side compatibility**, not a complete GA protocol migration or
live voice/model qualification. The outgoing connection still sends the beta
header and the legacy top-level voice/temperature session configuration.
[OpenAI's migration guide](https://developers.openai.com/api/docs/guides/realtime#beta-to-ga-migration)
requires removal of that header and updated session types/audio configuration
before GA use. Accepting new event names alone does not qualify a new model.

`list_models()` therefore remains empty. Select a model explicitly with provider
`config.model`; this connection-scoped selection is sent unchanged and is not
replaced by a recommendation. Per-call `ChatRequest.model` switching is not
implemented by this session-based adapter. No model availability or account
entitlement is inferred from a name. The examples below are historical beta
configuration examples, **not current recommendations**. No paid/live provider,
microphone, audio playback, or live endpoint acceptance test was performed.

### Historical beta model examples

| Model | Status | Best For |
|-------|---------|----------|
| `gpt-4o-realtime-preview-2024-12-17` | Preview | Development & testing, balanced performance |
| `gpt-4o-mini-realtime-preview-2024-12-17` | Preview | Cost-sensitive applications, faster response |

### Voice Options

**Standard voices** (available in all OpenAI products):
- `alloy` - Neutral and balanced
- `echo` - Warm and engaging
- `shimmer` - Energetic and expressive

**Realtime-exclusive voices** (only in Realtime API):
- `marin` - Professional and clear
- `cedar` - Natural and conversational

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `api_key` | str | `$OPENAI_API_KEY` | OpenAI API key |
| `model` | str | `gpt-4o-realtime-preview-2024-12-17` | Model to use |
| `voice` | str | `alloy` | Voice selection |
| `temperature` | float | `0.7` | Response randomness (0.0-1.0) |
| `max_tokens` | int | None | Optional output token limit |
| `session_config` | dict | `{}` | Additional OpenAI session parameters |

See [examples/config_examples.yaml](examples/config_examples.yaml) for more configuration patterns.

## Usage

### Sending Audio

```python
# Audio input format: PCM16, 24kHz, mono
async with AmplifierSession(config=config) as session:
    response = await session.execute({
        "role": "user",
        "content": [
            {
                "type": "audio",
                "data": audio_bytes,  # PCM16 audio data
                "format": "pcm16",
                "sample_rate": 24000
            }
        ]
    })

    # Extract audio response
    audio_output = response.raw["audio_data"]
    transcript = response.raw["transcript"]
```

### Function Calling

The provider integrates with Amplifier's tool system:

```python
config = {
    # ... session and provider config ...
    "tools": [{
        "module": "tool-web",
        "source": "git+https://github.com/microsoft/amplifier-module-tool-web@main"
    }]
}

async with AmplifierSession(config=config) as session:
    # Voice input triggers tool call
    response = await session.execute({
        "role": "user",
        "content": [{"type": "audio", "data": audio_input}]
    })

    # Model can call tools and respond with voice
    # Tool execution handled automatically by Amplifier
```

See [docs/FUNCTION_CALLING.md](docs/FUNCTION_CALLING.md) for detailed patterns.

### Multiple Conversation Turns

The provider maintains a persistent WebSocket session:

```python
async with AmplifierSession(config=config) as session:
    # Turn 1
    response1 = await session.execute({
        "role": "user",
        "content": [{"type": "audio", "data": audio1}]
    })

    # Turn 2 (same session)
    response2 = await session.execute({
        "role": "user",
        "content": [{"type": "audio", "data": audio2}]
    })

    # Session closed automatically on context exit
```

## Architecture

### Provider Response Structure

The provider returns audio in the `raw` field of `ProviderResponse`:

```python
ProviderResponse(
    content=transcript,              # Text transcript for existing systems
    raw={
        "audio_data": bytes,         # PCM16 audio bytes
        "audio_format": "pcm16",     # Format specification
        "sample_rate": 24000,        # Sample rate in Hz
        "transcript": str,           # Text version
        "session_id": str,           # WebSocket session ID
        "websocket_response": dict   # Full OpenAI response
    },
    usage={"input": tokens, "output": tokens},
    content_blocks=[TextBlock(text=transcript)]
)
```

### Components

- **`provider.py`**: Main provider implementing Amplifier's provider protocol
- **`websocket.py`**: OpenAI Realtime WebSocket protocol handler
- **`audio_codec.py`**: PCM16 audio encoding/decoding utilities
- **`session_mgmt.py`**: WebSocket session lifecycle management
- **`exceptions.py`**: Provider-specific error types

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed design documentation.

### Philosophy Alignment

This provider follows Amplifier's kernel philosophy:

- **Mechanism, not policy**: Handles WebSocket protocol, not audio I/O decisions
- **Zero kernel changes**: Pure edge implementation using existing provider contract
- **No module modifications**: Works with all existing Amplifier components unchanged
- **Tool integration**: Uses standard tool mechanism for function calling
- **Prototype at edges**: Audio in `raw` field until pattern proven by multiple providers

## Audio Format

**Input format** (to provider):
- Encoding: PCM16 (16-bit signed integer)
- Sample rate: 24,000 Hz
- Channels: Mono (1 channel)
- Byte order: Little-endian

**Output format** (from provider):
- Same as input format
- Includes transcript for debugging and logging

See [docs/AUDIO_FORMAT.md](docs/AUDIO_FORMAT.md) for encoding/decoding details.

## Development

### Running Tests

```bash
# Install dev dependencies
uv sync --dev

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=amplifier_module_provider_openai_realtime

# Run specific test file
uv run pytest tests/test_provider.py -v
```

### Integration Tests

Integration tests require an OpenAI API key:

```bash
export OPENAI_API_KEY="sk-..."
uv run pytest tests/test_integration.py
```

**Note**: Integration tests make real API calls and incur costs.

## Troubleshooting

### Connection Issues

**Problem**: `WebSocketConnectionError: Failed to connect`

**Solutions**:
- Verify API key: `echo $OPENAI_API_KEY`
- Check network connectivity
- Review firewall settings (needs WSS on port 443)

### Audio Format Errors

**Problem**: `AudioFormatError: Expected PCM16 format`

**Solutions**:
- Verify audio is PCM16, 24kHz, mono
- Use `audio_codec.py` utilities for conversion
- Check byte order (should be little-endian)

### Session Initialization Fails

**Problem**: `SessionInitializationError: Could not initialize session`

**Solutions**:
- Check model availability (preview models may have limits)
- Verify voice selection (must be one of 5 supported voices)
- Review OpenAI API status

See [docs/EXAMPLES.md](docs/EXAMPLES.md) for troubleshooting examples.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - Module design and component overview
- [API Contract](docs/API_CONTRACT.md) - Provider protocol implementation details
- [Audio Format](docs/AUDIO_FORMAT.md) - Audio encoding/decoding specifications
- [Session Lifecycle](docs/SESSION_LIFECYCLE.md) - WebSocket connection management
- [Function Calling](docs/FUNCTION_CALLING.md) - Tool integration patterns
- [Examples](docs/EXAMPLES.md) - Usage recipes and troubleshooting

## Limitations

Current implementation has these limitations:

- **Audio format**: PCM16 only (no MP3/Opus/etc)
- **Sample rate**: Fixed at 24kHz (OpenAI Realtime requirement)
- **Interaction model**: Turn-based (not streaming/interruptible)
- **Knowledge bases**: Not supported by OpenAI Realtime API
- **Custom voices**: Voice cloning not available

These are exploratory phase limitations. Future iterations may address them based on user needs.

## Contributing

This project follows the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for contribution guidelines.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.

## License

MIT License - see [LICENSE](LICENSE) for details.

### Core provider contract

The adapter accepts Core 2.0.1 typed text requests and returns typed content, usage, and function calls. Direct callers retain `response.raw` for audio bytes and the original WebSocket response. `raw: true` adds optional redacted request capture to the standard LLM events; capture defaults to false. Model catalog limits are left unknown rather than invented.

This update preserves the existing Realtime endpoint/session protocol. It does not qualify the current voice service, physical audio devices, or a newer Realtime wire protocol.

Initialization accepts the documented `session.created` → `conversation.created`
→ `session.updated` sequence. Only `session.updated` confirms configuration.
The intervening conversation event must have a valid envelope and can occur
once, after session creation; its optional resource fields are validated when
present. At most three initialization events are consumed. Unknown, malformed,
error, or excess events fail closed. This is an offline protocol compatibility
check, not a live beta handshake or GA migration. Caller cancellation/timeouts
still close the connection; no new wall-clock timeout policy is introduced.
