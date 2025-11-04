# Architecture

This document describes the design and component structure of the OpenAI Realtime provider module.

## Design Philosophy

The provider follows Amplifier's kernel philosophy:

- **Mechanism, not policy**: Implements WebSocket protocol, audio I/O policy lives in application
- **Zero kernel changes**: Pure edge implementation using existing provider contract
- **Prototype at edges**: Audio in `raw` field until multiple audio providers prove convergence
- **Ruthless simplicity**: Only essential features, no future-proofing
- **Clear boundaries**: Clean separation between provider and application concerns

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  Application Layer                                      │
│  (amplifier-app-voice or custom app)                    │
│  - Audio capture (microphone)                           │
│  - Audio playback (speakers)                            │
│  - User interaction                                     │
└─────────────────┬───────────────────────────────────────┘
                  │ AmplifierSession API
                  ▼
┌─────────────────────────────────────────────────────────┐
│  OpenAIRealtimeProvider                                 │
│  - Implements Provider protocol                         │
│  - WebSocket session management                         │
│  - Audio format handling                                │
│  - Tool call integration                                │
└─────────────────┬───────────────────────────────────────┘
                  │ WebSocket (WSS)
                  ▼
┌─────────────────────────────────────────────────────────┐
│  OpenAI Realtime API                                    │
│  wss://api.openai.com/v1/realtime                       │
└─────────────────────────────────────────────────────────┘
```

## Component Structure

### Module Organization

```
amplifier_module_provider_openai_realtime/
├── __init__.py              # mount() entry point
├── provider.py              # Main provider class
├── websocket.py             # WebSocket protocol handler
├── audio_codec.py           # Audio encoding/decoding
├── session_mgmt.py          # Session lifecycle management
└── exceptions.py            # Provider-specific exceptions
```

### Component Responsibilities

#### `__init__.py` - Module Entry Point

**Responsibilities**:
- Exports `mount()` function for Amplifier kernel
- Initializes provider with configuration
- Returns cleanup function for teardown

**Interface**:
```python
async def mount(
    coordinator: ModuleCoordinator,
    config: dict[str, Any] | None = None
) -> Callable[[], Awaitable[None]]:
    """
    Mount the provider module.

    Args:
        coordinator: Amplifier module coordinator
        config: Provider configuration dict

    Returns:
        Async cleanup function
    """
```

#### `provider.py` - Provider Implementation

**Responsibilities**:
- Implements Amplifier's `Provider` protocol
- Message format conversion
- Response construction
- Tool call parsing
- Event emission via coordinator

**Key class**:
```python
class OpenAIRealtimeProvider:
    """Main provider implementing Provider protocol."""

    name: str = "openai-realtime"

    async def complete(
        self,
        messages: list[dict[str, Any]],
        **kwargs
    ) -> ProviderResponse:
        """Send audio/text, receive audio response."""

    def parse_tool_calls(
        self,
        response: ProviderResponse
    ) -> list[ToolCall]:
        """Extract tool calls from response."""
```

**Response structure**:
```python
ProviderResponse(
    content=transcript,              # Text for existing systems
    raw={
        "audio_data": bytes,         # PCM16 audio
        "audio_format": "pcm16",
        "sample_rate": 24000,
        "transcript": str,
        "session_id": str,
        "websocket_response": dict
    },
    usage={"input": tokens, "output": tokens},
    content_blocks=[TextBlock(text=transcript)]
)
```

#### `websocket.py` - Protocol Handler

**Responsibilities**:
- WebSocket connection establishment
- OpenAI Realtime protocol implementation
- Audio frame send/receive
- Tool call transmission
- Error handling and reconnection

**Key class**:
```python
class RealtimeWebSocket:
    """Handles OpenAI Realtime WebSocket protocol."""

    async def connect(
        self,
        api_key: str,
        model: str
    ) -> None:
        """Establish WebSocket connection."""

    async def send_audio(
        self,
        audio_data: bytes
    ) -> None:
        """Send audio input frame."""

    async def receive_audio(self) -> dict[str, Any]:
        """Receive audio response frame."""

    async def send_tool_result(
        self,
        tool_result: dict[str, Any]
    ) -> None:
        """Send tool execution result."""

    async def close(self) -> None:
        """Close WebSocket gracefully."""
```

#### `audio_codec.py` - Audio Utilities

**Responsibilities**:
- PCM16 encoding/decoding
- Sample rate validation
- Format detection
- Audio data validation

**Key functions**:
```python
def encode_pcm16(audio_array: np.ndarray) -> bytes:
    """Encode numpy array to PCM16 bytes."""

def decode_pcm16(audio_bytes: bytes) -> np.ndarray:
    """Decode PCM16 bytes to numpy array."""

def validate_audio_format(
    audio_data: bytes,
    expected_sample_rate: int = 24000
) -> bool:
    """Validate audio format and sample rate."""
```

#### `session_mgmt.py` - Session Lifecycle

**Responsibilities**:
- WebSocket session initialization
- Session instruction setting
- Connection reuse/pooling
- Graceful shutdown

**Key class**:
```python
class SessionManager:
    """Manages WebSocket session lifecycle."""

    async def initialize_session(
        self,
        instructions: str
    ) -> str:
        """Create new session with instructions."""

    async def get_or_create_connection(self) -> RealtimeWebSocket:
        """Lazy connection initialization."""

    async def cleanup(self) -> None:
        """Close all connections gracefully."""
```

#### `exceptions.py` - Error Types

**Provider-specific exceptions**:
```python
class WebSocketConnectionError(Exception):
    """WebSocket connection failed."""

class AudioFormatError(Exception):
    """Invalid audio format."""

class SessionInitializationError(Exception):
    """Session initialization failed."""
```

## Data Flow

### Audio Input Flow

```
1. App captures audio (microphone)
   ↓
2. App sends via session.execute({audio_data})
   ↓
3. Provider receives message
   ↓
4. SessionManager ensures WebSocket connected
   ↓
5. audio_codec validates format
   ↓
6. RealtimeWebSocket sends to OpenAI
   ↓
7. OpenAI processes audio
```

### Audio Output Flow

```
1. OpenAI sends audio response
   ↓
2. RealtimeWebSocket receives frame
   ↓
3. audio_codec decodes PCM16
   ↓
4. Provider constructs ProviderResponse
   ↓
5. Response returned to app
   ↓
6. App extracts audio from raw field
   ↓
7. App plays audio (speakers)
```

### Tool Call Flow

```
1. Audio input processed
   ↓
2. Model decides to call tool
   ↓
3. Provider parses tool call
   ↓
4. Amplifier executes tool
   ↓
5. Result sent back through WebSocket
   ↓
6. Model continues with audio response
```

## Session Lifecycle

### Initialization

```
1. mount() called by Amplifier kernel
2. Provider instance created
3. SessionManager initialized (no connection yet)
4. Provider mounted to coordinator
5. Cleanup function returned
```

### First Request

```
1. complete() called with audio
2. SessionManager creates WebSocket connection
3. Session initialized with instructions
4. Audio sent, response received
5. Connection kept alive
```

### Subsequent Requests

```
1. complete() called with audio
2. SessionManager reuses existing connection
3. Audio sent, response received
4. Connection remains open
```

### Teardown

```
1. Application closes session
2. Cleanup function invoked
3. WebSocket closed gracefully
4. Resources released
```

## Integration Points

### With Amplifier Core

**Provider protocol**:
- Implements `Provider` interface (name, complete, parse_tool_calls)
- Returns `ProviderResponse` with standard structure
- Parses tool calls using standard `ToolCall` format

**Module coordinator**:
- Emits events: `provider:request`, `provider:response`, `provider:error`
- Mounts under `"providers"` path with name `"openai-realtime"`

### With Existing Orchestrators

**Compatible with**:
- `loop-basic` - Turn-based audio conversation
- `loop-streaming` - Streaming text transcript
- `loop-events` - Event-driven architecture

**No modifications needed**: Orchestrators see audio as standard provider response.

### With Existing Tools

**Full compatibility**:
- Tools receive calls via standard mechanism
- Tool results sent back via WebSocket
- Voice input can trigger any Amplifier tool
- Tools return results (can include audio suggestions)

## Performance Characteristics

### Latency

**Typical round-trip**:
- Audio capture: ~100ms (app layer)
- Network: ~200-300ms (varies)
- OpenAI processing: ~500-1000ms
- Audio playback: ~100ms (app layer)
- **Total: ~1-1.5 seconds typical**

### Token Usage

**Audio tokens**:
- Input: ~50 tokens per second of audio
- Output: ~50 tokens per second of audio
- Varies by actual speech content

### Connection Management

**WebSocket lifecycle**:
- One persistent connection per provider instance
- Connection reused across turns
- Automatic reconnection on failure
- Graceful shutdown on session end

## Extensibility Points

### Future Audio Formats

To support additional formats:
1. Extend `audio_codec.py` with new codecs
2. Add format detection logic
3. Update `ProviderResponse.raw` structure
4. Document in [AUDIO_FORMAT.md](AUDIO_FORMAT.md)

### Streaming Support

To add streaming (future):
1. Extend provider with `complete_stream()` method
2. Yield audio chunks incrementally
3. Requires orchestrator awareness
4. Only add after proving turn-based pattern

### Multiple Sessions

To support session pooling (future):
1. Extend `SessionManager` with pool
2. Add session selection logic
3. Track session state separately
4. Only add if needed

## Design Decisions

### Why Audio in Raw Field?

**Decision**: Store audio in `ProviderResponse.raw` instead of new `AudioBlock` content type.

**Rationale**:
- Zero kernel changes (pure edge implementation)
- Follows "two-implementation rule" (wait for second audio provider)
- Existing systems see text transcript
- Voice apps can access audio explicitly
- Can promote to `AudioBlock` later if pattern proven

### Why Turn-Based Not Streaming?

**Decision**: Implement turn-based conversation, not real-time streaming/interruption.

**Rationale**:
- Simpler implementation (exploratory phase)
- Sufficient for initial use cases
- Can add streaming later if validated
- Avoids complex orchestrator changes

### Why Persistent WebSocket?

**Decision**: Maintain one WebSocket connection across multiple turns.

**Rationale**:
- OpenAI Realtime API designed for sessions
- Reduces connection overhead
- Preserves conversation context
- Simpler than connection-per-request

### Why PCM16 Only?

**Decision**: Support PCM16 format only initially.

**Rationale**:
- OpenAI Realtime API native format
- Simple encoding/decoding
- No compression overhead
- Can add formats later if needed

## Testing Strategy

### Unit Tests

Test each component in isolation:
- `provider.py`: Mock WebSocket, test protocol implementation
- `websocket.py`: Mock OpenAI responses, test protocol
- `audio_codec.py`: Test encoding/decoding with sample data
- `session_mgmt.py`: Test lifecycle without real connections

### Integration Tests

Test end-to-end flow:
- Real OpenAI API calls (requires API key)
- Audio round-trip (send PCM16, receive PCM16)
- Tool calling integration
- Error handling scenarios

### Performance Tests

Measure characteristics:
- Latency distribution
- Token usage accuracy
- Connection stability
- Memory usage

## Security Considerations

### API Key Handling

- API key from config or environment
- Never logged or exposed
- Passed securely to WebSocket

### Audio Data

- Audio not persisted by provider
- Transmitted encrypted (WSS)
- Controlled by application layer

### Tool Execution

- Tools execute in Amplifier's security context
- Provider validates tool results
- No special privileges for voice

## See Also

- [API Contract](API_CONTRACT.md) - Provider protocol implementation
- [Audio Format](AUDIO_FORMAT.md) - Audio encoding specifications
- [Session Lifecycle](SESSION_LIFECYCLE.md) - WebSocket management details
- [Function Calling](FUNCTION_CALLING.md) - Tool integration patterns
