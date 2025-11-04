# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

### Added

- Initial OpenAI Realtime API provider implementation
- WebSocket-based audio streaming to/from OpenAI
- Turn-based voice conversation support
- PCM16 audio format handling (24kHz, mono)
- Five voice options: alloy, echo, shimmer, marin, cedar
- Full function calling support via Amplifier tool system
- Persistent WebSocket session across conversation turns
- Automatic system message to session instruction conversion
- Audio data in ProviderResponse.raw field (zero kernel changes)
- Text transcript for compatibility with existing systems
- Comprehensive documentation (ARCHITECTURE, API_CONTRACT, AUDIO_FORMAT, etc.)
- Working examples (basic_conversation, with_tools)
- Configuration examples for various use cases

### Implementation Details

- Implements standard Amplifier Provider protocol
- Zero modifications to amplifier-core or existing modules
- Audio stored in raw field (prototype-at-edges approach)
- WebSocket session manager with graceful lifecycle
- Error handling for connection, audio format, and session issues
- Event emission for observability (provider:request/response/error)

### Limitations

- Audio format: PCM16 only (no MP3/Opus support)
- Sample rate: Fixed at 24kHz (OpenAI requirement)
- Interaction model: Turn-based (not streaming/interruptible)
- Knowledge bases: Not supported by OpenAI Realtime API
- Custom voices: Voice cloning not available

### Known Issues

None yet - this is the initial release.

## Future Versions

### Planned for 0.2.0

- Streaming audio support (if validated as needed)
- Additional audio format support (if requested)
- Enhanced error recovery strategies
- Performance optimizations based on usage

### Considering for Future

- Interruption handling (requires orchestrator changes)
- Session pooling (if needed for scale)
- Audio preprocessing hooks (if requested)
- Multiple simultaneous sessions (if use case emerges)

---

[0.1.0]: https://github.com/robotdad/amplifier-module-provider-openai-realtime/releases/tag/v0.1.0
