# DDD Plan: OpenAI Realtime Provider Module

## Problem Statement

**What we're solving**: Current Amplifier providers are text-based and cannot handle real-time audio conversations. Voice applications require a full STT→LLM→TTS pipeline with high latency.

**Why it matters**: OpenAI's Realtime API processes audio natively (speech-to-speech) with ultra-low latency, enabling natural voice conversations with full function calling support.

**User value**:
- Developers can build voice-first applications within Amplifier
- Natural conversation flow with minimal latency
- Full integration with Amplifier's tool system
- Simple configuration (just another provider)

**Target use case**: Exploratory voice assistant applications (desktop, embedded devices) with voice input/output and tool calling capabilities.

## Proposed Solution

**High-level approach**: Create a new provider module that implements Amplifier's existing provider contract while handling audio I/O through OpenAI's Realtime WebSocket API.

**Key innovation**: Store audio in the `raw` field of `ProviderResponse` (no kernel changes required). The provider maintains a persistent WebSocket session and returns both audio and text transcripts.

**Integration model**:
```
User speaks → App captures audio → Provider sends to OpenAI WebSocket →
→ Model responds with audio + transcript → App plays audio
```

**Philosophy alignment**:
- ✅ Zero kernel changes (pure edge implementation)
- ✅ No existing module modifications
- ✅ Follows "prototype at edges first" principle
- ✅ Can promote audio to ContentBlock later if multiple audio providers emerge

## Alternatives Considered

### Alternative 1: Add AudioBlock to Kernel ContentBlockUnion
**Approach**: Extend kernel's content type system with native audio support.

**Pros**: Audio becomes first-class citizen, all modules understand it

**Cons**:
- ❌ Violates "two-implementation rule" (we're the only audio provider)
- ❌ Requires kernel changes before proving pattern
- ❌ Premature abstraction

**Decision**: Rejected - Prototype at edges first per kernel philosophy

### Alternative 2: Streaming Provider Protocol
**Approach**: Extend provider contract with `complete_stream()` method for incremental audio chunks.

**Pros**: True real-time streaming, lower latency, interruptible

**Cons**:
- ❌ Requires kernel protocol changes
- ❌ Orchestrator must handle streaming
- ❌ Complex tool calling integration
- ❌ No convergence evidence (only one streaming audio provider)

**Decision**: Rejected - Too complex for exploratory phase, can add later if validated

### Alternative 3: Separate AudioProvider Protocol
**Approach**: Create parallel audio provider protocol separate from text providers.

**Pros**: Clean separation of concerns

**Cons**:
- ❌ Creates parallel hierarchy
- ❌ Unclear tool calling integration
- ❌ Unnecessary complexity
- ❌ Two protocols to maintain

**Decision**: Rejected - Unnecessary abstraction, existing protocol sufficient

## Architecture & Design

### Key Interfaces

**Provider Contract** (existing, no changes):
```python
class Provider(Protocol):
    @property
    def name(self) -> str: ...

    async def complete(self, messages: list[dict], **kwargs) -> ProviderResponse: ...

    def parse_tool_calls(self, response: ProviderResponse) -> list[ToolCall]: ...
```

**Mount Function** (required entry point):
```python
async def mount(coordinator: ModuleCoordinator, config: dict | None) -> cleanup_fn:
    """
    Initialize provider with WebSocket connection.

    Args:
        coordinator: Module coordinator for mounting
        config: Provider config (api_key, model, voice, temperature)

    Returns:
        Async cleanup function for WebSocket teardown
    """
```

**Audio Representation** (in raw field):
```python
ProviderResponse(
    content=transcript,  # Text for existing systems
    raw={
        "audio_data": bytes,      # PCM16 audio bytes
        "audio_format": "pcm16",  # Format specification
        "sample_rate": 24000,     # OpenAI Realtime uses 24kHz
        "transcript": str,        # Text version of audio
        "session_id": str,        # WebSocket session ID
        "websocket_response": {}  # Full response object
    },
    usage={"input": tokens, "output": tokens},
    content_blocks=[TextBlock(text=transcript)]
)
```

### Module Boundaries

**What this provider module owns**:
- OpenAI Realtime WebSocket protocol implementation
- Session management (connection lifecycle)
- Audio format handling (PCM16 encoding/decoding)
- System message → session instruction conversion
- Function calling integration (via existing tool mechanism)
- Audio buffering for turn-based conversation

**What this provider does NOT own**:
- Audio capture (microphone) - App layer responsibility
- Audio playback (speakers) - App layer responsibility
- Audio streaming policy - App layer decision
- Real-time interruption handling - App layer or future orchestrator

**Clear "studs"** (connection points):
1. `mount(coordinator, config)` - Entry point
2. `complete(messages, **kwargs)` - Core interaction
3. `parse_tool_calls(response)` - Tool integration
4. `raw` field structure - Audio data contract

### Data Models

**Configuration Schema**:
```python
{
    "api_key": str,                    # OpenAI API key (or $OPENAI_API_KEY)
    "model": str,                      # e.g., "gpt-4o-realtime-preview-2024-12-17"
    "voice": str,                      # alloy, echo, shimmer, marin, cedar
    "temperature": float,              # 0.0-1.0, default 0.7
    "max_tokens": int | None,          # Optional output limit
    "session_config": dict | None      # Additional OpenAI session params
}
```

**Audio Input Format** (messages list):
```python
[
    {
        "role": "user",
        "content": [
            {"type": "audio", "data": bytes}  # PCM16 audio data
        ]
    }
]
```

**WebSocket Session State**:
```python
{
    "session_id": str,          # OpenAI session ID
    "websocket": WebSocket,     # Active connection
    "connected": bool,          # Connection status
    "instructions": str,        # Session instructions (from system messages)
}
```

### Component Architecture

```
OpenAIRealtimeProvider
├── __init__.py               # mount() entry point
├── provider.py              # Main provider class
├── websocket.py             # WebSocket protocol handler
├── audio_codec.py           # PCM16 encoding/decoding utilities
└── session_mgmt.py          # Session lifecycle management
```

**Key classes**:

```python
# provider.py
class OpenAIRealtimeProvider:
    """Main provider implementing Provider protocol."""

    name = "openai-realtime"

    def __init__(self, api_key, config, coordinator):
        self.session_manager = SessionManager(api_key, config)
        self.coordinator = coordinator

    async def complete(self, messages, **kwargs) -> ProviderResponse:
        """Send audio/text, receive audio response."""

    def parse_tool_calls(self, response) -> list[ToolCall]:
        """Extract tool calls from response."""

# websocket.py
class RealtimeWebSocket:
    """Handles OpenAI Realtime WebSocket protocol."""

    async def connect(self, api_key, model):
        """Establish WebSocket connection."""

    async def send_audio(self, audio_data):
        """Send audio input to OpenAI."""

    async def receive_audio(self) -> dict:
        """Receive audio response from OpenAI."""

    async def send_tool_result(self, tool_result):
        """Send tool execution result."""

# session_mgmt.py
class SessionManager:
    """Manages WebSocket session lifecycle."""

    async def initialize_session(self, instructions):
        """Create new session with instructions."""

    async def get_or_create_connection(self):
        """Lazy connection initialization."""

    async def cleanup(self):
        """Close WebSocket gracefully."""
```

## Files to Change

### Non-Code Files (Phase 2)

**Within amplifier-module-provider-openai-realtime/**:
- [x] README.md - Already has basic structure, needs:
  - [ ] Detailed API usage examples
  - [ ] Configuration reference
  - [ ] Audio format specifications
  - [ ] Function calling examples
  - [ ] Troubleshooting guide
  - [ ] Migration from text providers

- [ ] docs/ - Create new directory with:
  - [ ] docs/ARCHITECTURE.md - Module design and components
  - [ ] docs/API_CONTRACT.md - Provider contract implementation details
  - [ ] docs/AUDIO_FORMAT.md - Audio encoding/decoding specifications
  - [ ] docs/SESSION_LIFECYCLE.md - WebSocket session management
  - [ ] docs/FUNCTION_CALLING.md - Tool integration patterns
  - [ ] docs/EXAMPLES.md - Usage examples and recipes

- [x] pyproject.toml - Already configured, needs:
  - [ ] Verify dependency versions
  - [ ] Add any missing dependencies (websockets confirmed)

- [ ] CHANGELOG.md - Create for version tracking

- [ ] examples/ - Create directory with:
  - [ ] examples/basic_conversation.py - Simple voice interaction
  - [ ] examples/with_tools.py - Function calling example
  - [ ] examples/config_examples.yaml - Various configurations

### Code Files (Phase 4)

**Within amplifier-module-provider-openai-realtime/src/amplifier_module_provider_openai_realtime/**:

- [x] __init__.py - Has mount() stub, needs:
  - [ ] Implement full mount() function
  - [ ] Config validation
  - [ ] Provider initialization
  - [ ] Cleanup function

- [ ] provider.py - **NEW FILE** - Main provider implementation:
  - [ ] OpenAIRealtimeProvider class
  - [ ] complete() method (audio I/O)
  - [ ] parse_tool_calls() method
  - [ ] Message format conversion
  - [ ] Event emission (via coordinator)

- [ ] websocket.py - **NEW FILE** - WebSocket protocol:
  - [ ] RealtimeWebSocket class
  - [ ] Connection establishment
  - [ ] Send/receive audio
  - [ ] Send/receive tool calls
  - [ ] Error handling

- [ ] audio_codec.py - **NEW FILE** - Audio utilities:
  - [ ] PCM16 encoding/decoding
  - [ ] Sample rate conversion (if needed)
  - [ ] Audio validation
  - [ ] Format detection

- [ ] session_mgmt.py - **NEW FILE** - Session lifecycle:
  - [ ] SessionManager class
  - [ ] Session initialization
  - [ ] Instruction setting
  - [ ] Connection pooling/reuse
  - [ ] Graceful shutdown

- [ ] exceptions.py - **NEW FILE** - Provider-specific exceptions:
  - [ ] WebSocketConnectionError
  - [ ] AudioFormatError
  - [ ] SessionInitializationError

**Within amplifier-module-provider-openai-realtime/tests/**:

- [ ] test_provider.py - Provider contract tests
- [ ] test_websocket.py - WebSocket protocol tests
- [ ] test_audio_codec.py - Audio encoding/decoding tests
- [ ] test_session_mgmt.py - Session lifecycle tests
- [ ] test_integration.py - End-to-end tests (requires API key)

## Philosophy Alignment

### Ruthless Simplicity

**Start minimal**:
- ✅ No kernel changes - work within existing contract
- ✅ Audio in raw field (not new content type yet)
- ✅ Basic turn-based conversation (not streaming initially)
- ✅ PCM16 only (not multiple audio formats)
- ✅ Session per provider instance (not session pooling)

**Avoid future-proofing**:
- ❌ NOT building: Streaming support (wait for need)
- ❌ NOT building: Multiple audio format support (YAGNI)
- ❌ NOT building: Advanced interruption handling (app layer)
- ❌ NOT building: Audio preprocessing/effects (app layer)
- ❌ NOT building: Session pooling/multiplexing (premature optimization)

**Clear over clever**:
- Simple WebSocket wrapper, not elaborate state machine
- Direct OpenAI API mapping, minimal abstractions
- Explicit error messages with context
- Straightforward audio buffering

### Modular Design

**Bricks** (self-contained pieces):
- `provider.py` - Provider contract implementation
- `websocket.py` - OpenAI WebSocket protocol
- `audio_codec.py` - Audio format handling
- `session_mgmt.py` - Session lifecycle

**Studs** (connection points):
- `mount(coordinator, config)` - Amplifier entry
- `complete(messages, **kwargs)` - Core interaction
- `raw` field structure - Audio data contract
- Provider protocol - Standard interface

**Regeneratable**:
- Each component can be rewritten from its spec
- Clear interfaces between components
- No hidden dependencies
- Documentation defines behavior

### Kernel Philosophy Compliance

**Mechanism, not policy** ✅:
- Provider implements WebSocket protocol (mechanism)
- App decides when to send audio (policy)
- App decides how to capture/play audio (policy)

**Don't break modules** ✅:
- Zero changes to existing modules
- Backward compatible
- Optional feature

**Policy at edges** ✅:
- Audio capture: App layer
- Audio playback: App layer
- Interruption: App layer
- Format selection: Provider config

**Two-implementation rule** ✅:
- Waiting for second audio provider before promoting to kernel
- Prototype proves pattern first

## Test Strategy

### Unit Tests

**provider.py tests**:
- mount() function with various configs
- complete() with text messages
- complete() with audio messages
- parse_tool_calls() extraction
- Error handling (bad config, missing API key)

**websocket.py tests**:
- Connection establishment
- Send audio frame
- Receive audio response
- Tool call send/receive
- Reconnection on failure
- Graceful shutdown

**audio_codec.py tests**:
- PCM16 encoding/decoding
- Sample rate validation
- Format detection
- Invalid audio handling

**session_mgmt.py tests**:
- Session initialization
- Instruction setting
- Connection reuse
- Cleanup

### Integration Tests

**End-to-end flow**:
1. Initialize provider with config
2. Send audio input
3. Receive audio output
4. Verify transcript
5. Test tool calling
6. Cleanup

**Error scenarios**:
- Invalid API key
- Network failure
- Malformed audio
- Tool call errors

**Note**: Integration tests require `OPENAI_API_KEY` environment variable

### User Testing

**Manual verification**:
1. Install provider: `uv pip install -e .`
2. Create test script with audio file
3. Send audio, receive audio response
4. Verify transcript matches audio
5. Test tool calling with sample function
6. Check WebSocket logs for correctness

**Success criteria**:
- Audio input processed correctly
- Audio output playable
- Transcript accurate
- Tools execute properly
- Graceful error handling

## Implementation Approach

### Phase 2 (Documentation)

**Order matters** (dependencies flow):

1. **Core specifications** (define contracts):
   - docs/API_CONTRACT.md
   - docs/AUDIO_FORMAT.md
   - docs/ARCHITECTURE.md

2. **Implementation guides** (how to use):
   - docs/SESSION_LIFECYCLE.md
   - docs/FUNCTION_CALLING.md
   - README.md updates

3. **Examples** (concrete usage):
   - examples/basic_conversation.py
   - examples/with_tools.py
   - docs/EXAMPLES.md

4. **Reference**:
   - CHANGELOG.md
   - examples/config_examples.yaml

### Phase 4 (Code Implementation)

**Implementation chunks** (dependency order):

**Chunk 1: Core Infrastructure**
- exceptions.py (no dependencies)
- audio_codec.py (no dependencies)
- session_mgmt.py (depends on exceptions)

**Chunk 2: WebSocket Protocol**
- websocket.py (depends on exceptions, audio_codec, session_mgmt)

**Chunk 3: Provider Implementation**
- provider.py (depends on all above)
- __init__.py mount() (depends on provider.py)

**Chunk 4: Testing**
- Unit tests (parallel with implementation)
- Integration tests (after provider complete)

**Verification after each chunk**:
- Run tests
- Check imports work
- Verify against specs

## Success Criteria

### Functional Requirements
- ✅ Provider mounts successfully via Amplifier
- ✅ Sends audio to OpenAI, receives audio back
- ✅ Returns both audio and transcript
- ✅ Tool calling works with voice input
- ✅ Multiple conversation turns work
- ✅ Graceful error handling

### Non-Functional Requirements
- ✅ Latency acceptable for exploratory use (<2 seconds typical)
- ✅ Clean WebSocket teardown (no leaked connections)
- ✅ Clear error messages with context
- ✅ Tests pass consistently

### Philosophy Requirements
- ✅ Zero kernel changes
- ✅ Zero existing module changes
- ✅ Simple, readable code
- ✅ Clear module boundaries
- ✅ Documentation as specification

### Integration Requirements
- ✅ Works with amplifier-app-voice
- ✅ Works with existing tools (filesystem, web, etc.)
- ✅ Compatible with existing orchestrators
- ✅ Standard provider configuration

## Risks & Mitigations

### Risk 1: WebSocket Connection Stability
**Issue**: Persistent WebSocket may fail silently or disconnect

**Mitigation**:
- Implement connection health checks
- Automatic reconnection on failure
- Clear error messages to user
- Log all WebSocket events

### Risk 2: Audio Format Mismatches
**Issue**: App sends wrong format, provider expects PCM16

**Mitigation**:
- Validate audio format on input
- Clear error messages about expected format
- Document format requirements prominently
- Provide audio validation utility

### Risk 3: Tool Call Integration Complexity
**Issue**: Tool calls might not work smoothly with audio flow

**Mitigation**:
- Follow Anthropic provider pattern (proven)
- Test with simple tools first
- Document expected tool response format
- Provide tool calling examples

### Risk 4: Session State Management
**Issue**: Session state could get corrupted across turns

**Mitigation**:
- Keep session state minimal
- Validate state before each turn
- Provide session reset capability
- Log all state transitions

## Next Steps

✅ **Phase 1 Complete**: Planning approved

➡️ **Ready for Phase 2**: `/ddd:2-docs`

**Phase 2 will**:
- Update README.md with detailed usage
- Create docs/ directory with specifications
- Write examples showing usage patterns
- Create configuration reference

**After Phase 2**:
- Phase 3: Code planning (chunk-by-chunk implementation order)
- Phase 4: Code implementation (following plan)
- Phase 5: Testing and verification

---

**Plan Status**: ✅ Ready for user review and approval
