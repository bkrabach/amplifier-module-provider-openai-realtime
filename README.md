# amplifier-module-provider-openai-realtime

OpenAI Realtime API provider module for Amplifier - native speech-to-speech interactions.

## Overview

This provider module integrates OpenAI's Realtime API with Amplifier, enabling native speech-to-speech conversations without the traditional STT/LLM/TTS pipeline. The Realtime API processes audio directly for ultra-low latency voice interactions.

## Features

- **Native audio I/O**: Direct audio streaming to/from OpenAI
- **WebSocket protocol**: Real-time bidirectional communication
- **Function calling**: Full support for Amplifier's tool system
- **Voice selection**: Supports `alloy`, `echo`, `shimmer`, `marin`, `cedar`
- **Session management**: Automatic system message → session instruction conversion

## Installation

```bash
# Install from git (development)
uv pip install git+https://github.com/microsoft/amplifier-module-provider-openai-realtime@main

# Install editable (local development)
cd amplifier-module-provider-openai-realtime
uv pip install -e .
```

## Configuration

### Basic Usage

```python
config = {
    "session": {
        "orchestrator": "loop-streaming",
        "context": "context-simple"
    },
    "providers": [{
        "module": "provider-openai-realtime",
        "source": "git+https://github.com/microsoft/amplifier-module-provider-openai-realtime@main",
        "config": {
            "model": "gpt-4o-realtime-preview-2024-12-17",
            "voice": "alloy",
            "temperature": 0.7,
            "api_key": "${OPENAI_API_KEY}"  # Or set in environment
        }
    }]
}
```

### Available Models

| Model | Status | Best For |
|-------|---------|----------|
| `gpt-4o-realtime-preview-2024-12-17` | Preview | Development & testing |
| `gpt-4o-mini-realtime-preview-2024-12-17` | Preview | Cost-sensitive apps |

### Voice Options

**Standard voices**: `alloy`, `echo`, `shimmer`
**Realtime-exclusive**: `marin`, `cedar`

## Provider Contract

### Request Format

```python
{
    "type": "audio",
    "data": bytes,  # PCM16 audio data
    "format": "pcm16",  # Audio format
    "sample_rate": 24000  # Hz
}
```

### Response Format

```python
{
    "type": "audio",
    "data": bytes,  # PCM16 audio data
    "format": "pcm16",
    "transcript": str,  # Optional text transcript
    "sample_rate": 24000
}
```

## Architecture

### Components

- **`provider.py`**: Main provider implementation (mount point)
- **`websocket.py`**: OpenAI WebSocket protocol handler
- **`audio_codec.py`**: Audio encoding/decoding utilities
- **`session_mgmt.py`**: Session instruction management

### Philosophy Alignment

- **Mechanism, not policy**: Handles WebSocket protocol, not audio I/O
- **Kernel contract**: Follows standard provider interface
- **No kernel changes**: Pure module implementation
- **Tool integration**: Works with existing Amplifier tools

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Run with verbose output
uv run pytest -v
```

## Current Limitations

- **Audio format**: Currently supports PCM16 only
- **Sample rate**: Fixed at 24kHz
- **Knowledge bases**: Not supported by OpenAI Realtime API
- **Custom voices**: Voice cloning not available

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
