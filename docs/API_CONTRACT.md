# API Contract

This document specifies how the OpenAI Realtime provider implements Amplifier's provider protocol.

## Current implementation qualification

The historical protocol examples below predate the Core 2 typed-response repair.
The current implementation returns `ChatResponse` with `content: list[TextBlock]`,
typed `Usage`/`ToolCall`, and the preserved `raw` audio accessor.

The receiver now accepts current `response.output_audio.*` and
`response.output_audio_transcript.*`, plus legacy `response.audio.*` and
`response.audio_transcript.*` names.
See the explicit [compatibility boundary](../README.md#compatibility-boundary-and-model-selection).
Bytes come from individually decoded delta events, not the terminal response
object. `response.done` is the turn boundary; it contains usage and tool outputs.
`session.created` does not confirm a session update: the adapter waits for the
matching `session.updated` before sending a conversation item.

The offline tests prove serialized receive behavior, not current GA session
request compatibility, provider entitlement, physical audio, or live service
acceptance. The legacy outgoing session shape and beta header are unchanged.

## Provider Protocol

The provider implements Amplifier's `Provider` protocol defined in `amplifier-core`:

```python
@runtime_checkable
class Provider(Protocol):
    """Interface for LLM provider modules."""

    @property
    def name(self) -> str:
        """Provider name."""

    async def complete(
        self,
        messages: list[dict[str, Any]],
        **kwargs
    ) -> ProviderResponse:
        """Generate completion from messages."""

    def parse_tool_calls(
        self,
        response: ProviderResponse
    ) -> list[ToolCall]:
        """Parse tool calls from provider response."""
```

## Implementation Details

### Provider Name

```python
name: str = "openai-realtime"
```

**Usage**: Identifies the provider in logs, events, and configuration.

### complete() Method

**Signature**:
```python
async def complete(
    self,
    messages: list[dict[str, Any]],
    **kwargs
) -> ProviderResponse:
```

**Input - Messages Format**:

The provider accepts messages in Amplifier's standard format:

```python
[
    {
        "role": "system",
        "content": "You are a helpful assistant."
    },
    {
        "role": "user",
        "content": [
            {
                "type": "audio",
                "data": bytes,         # PCM16 audio data
                "format": "pcm16",     # Audio format
                "sample_rate": 24000   # Hz
            }
        ]
    },
    {
        "role": "assistant",
        "content": "Response text or audio"
    }
]
```

**Supported content types in user messages**:
- `{"type": "text", "text": str}` - Text input
- `{"type": "audio", "data": bytes, ...}` - Audio input

**System message handling**:
- Converted to OpenAI Realtime session instructions
- Set during WebSocket initialization
- Persists for entire session

**Output - ProviderResponse**:

```python
ProviderResponse(
    content=transcript,              # str - Text transcript
    raw={
        "audio_data": bytes,         # PCM16 audio bytes
        "audio_format": "pcm16",     # Format specification
        "sample_rate": 24000,        # Sample rate in Hz
        "transcript": str,           # Text version
        "session_id": str,           # WebSocket session ID
        "websocket_response": dict   # Full OpenAI response
    },
    usage={
        "input": int,                # Input tokens (audio + text)
        "output": int                # Output tokens (audio + text)
    },
    tool_calls=None | list[ToolCall],  # Extracted tool calls
    content_blocks=[                   # Content blocks
        TextBlock(text=transcript)
    ]
)
```

**Fields explained**:

| Field | Type | Description |
|-------|------|-------------|
| `content` | str | Text transcript for existing systems |
| `raw` | dict | Audio data and metadata (see below) |
| `usage` | dict | Token counts (input/output) |
| `tool_calls` | list\|None | Parsed tool calls if present |
| `content_blocks` | list | Standard content blocks (TextBlock) |

**raw field structure**:

| Key | Type | Description |
|-----|------|-------------|
| `audio_data` | bytes | PCM16 audio bytes |
| `audio_format` | str | Always "pcm16" |
| `sample_rate` | int | Always 24000 |
| `transcript` | str | Text transcript of audio |
| `session_id` | str | WebSocket session ID |
| `websocket_response` | dict | Full OpenAI response object |

### parse_tool_calls() Method

**Signature**:
```python
def parse_tool_calls(
    self,
    response: ProviderResponse
) -> list[ToolCall]:
```

**Behavior**:
- Extracts tool calls from `response.tool_calls` field
- Returns empty list if no tool calls
- Tool calls already parsed during `complete()`

**ToolCall format**:
```python
ToolCall(
    tool=str,          # Tool name
    arguments=dict,    # Tool arguments
    id=str            # Unique call ID
)
```

**Example**:
```python
[
    ToolCall(
        tool="get_weather",
        arguments={"location": "San Francisco"},
        id="call_abc123"
    )
]
```

## Message Conversion

### System Messages → Session Instructions

**Input**:
```python
{
    "role": "system",
    "content": "You are a helpful voice assistant. Be concise."
}
```

**Conversion**:
```python
instructions = "You are a helpful voice assistant. Be concise."
# Sent during WebSocket session.update with instructions field
```

**Notes**:
- System messages combined into single instructions string
- Set once during session initialization
- Persists for entire WebSocket session
- Multiple system messages concatenated with newlines

### User Messages → Audio Input

**Text input**:
```python
{
    "role": "user",
    "content": [{"type": "text", "text": "Hello"}]
}
```

**Converted to**:
```json
{
    "type": "conversation.item.create",
    "item": {
        "type": "message",
        "role": "user",
        "content": [
            {"type": "input_text", "text": "Hello"}
        ]
    }
}
```

**Audio input**:
```python
{
    "role": "user",
    "content": [
        {
            "type": "audio",
            "data": audio_bytes,
            "format": "pcm16",
            "sample_rate": 24000
        }
    ]
}
```

**Converted to**:
```json
{
    "type": "conversation.item.create",
    "item": {
        "type": "message",
        "role": "user",
        "content": [
            {
                "type": "input_audio",
                "audio": "base64_encoded_audio"
            }
        ]
    }
}
```

### OpenAI Response → ProviderResponse

**OpenAI WebSocket response**:
```json
{
    "type": "response.done",
    "response": {
        "id": "resp_abc123",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "audio",
                        "audio": "base64_audio",
                        "transcript": "Hello there!"
                    }
                ]
            }
        ],
        "usage": {
            "input_tokens": 150,
            "output_tokens": 200
        }
    }
}
```

**Converted to ProviderResponse**:
```python
ProviderResponse(
    content="Hello there!",
    raw={
        "audio_data": decode_base64(base64_audio),
        "audio_format": "pcm16",
        "sample_rate": 24000,
        "transcript": "Hello there!",
        "session_id": "sess_xyz",
        "websocket_response": {...}  # Full response
    },
    usage={"input": 150, "output": 200},
    content_blocks=[TextBlock(text="Hello there!")]
)
```

## Tool Call Protocol

### Tool Call Detection

**OpenAI response with function call**:
```json
{
    "type": "response.function_call_arguments.done",
    "call_id": "call_abc123",
    "name": "get_weather",
    "arguments": "{\"location\":\"San Francisco\"}"
}
```

**Parsed to**:
```python
ToolCall(
    tool="get_weather",
    arguments={"location": "San Francisco"},
    id="call_abc123"
)
```

### Tool Result Submission

**After Amplifier executes tool**:
```python
tool_result = {"temperature": 72, "condition": "sunny"}
```

**Sent via WebSocket**:
```json
{
    "type": "conversation.item.create",
    "item": {
        "type": "function_call_output",
        "call_id": "call_abc123",
        "output": "{\"temperature\":72,\"condition\":\"sunny\"}"
    }
}
```

**OpenAI continues with audio response**:
```json
{
    "type": "response.audio.done",
    "audio": "base64_audio",
    "transcript": "It's 72 degrees and sunny in San Francisco."
}
```

## Error Handling

### Connection Errors

**Raised**: `WebSocketConnectionError`

**When**:
- WebSocket connection fails
- Network issues
- Invalid API key

**Behavior**:
- Error logged with context
- Event emitted: `provider:error`
- Exception propagated to caller

### Audio Format Errors

**Raised**: `AudioFormatError`

**When**:
- Audio not PCM16
- Wrong sample rate
- Invalid audio data

**Behavior**:
- Error logged with details
- Event emitted: `provider:validation_error`
- Exception propagated to caller

### Session Initialization Errors

**Raised**: `SessionInitializationError`

**When**:
- Session creation fails
- Invalid model specified
- Unsupported voice

**Behavior**:
- Error logged
- Event emitted: `provider:error`
- Exception propagated to caller

## Event Emission

The provider emits events via the coordinator:

### provider:request

**Emitted**: Before WebSocket send

**Data**:
```python
{
    "provider": "openai-realtime",
    "model": "gpt-4o-realtime-preview-2024-12-17",
    "messages": [...],      # Input messages
    "session_id": "sess_xyz"
}
```

### provider:response

**Emitted**: After successful response

**Data**:
```python
{
    "provider": "openai-realtime",
    "model": "gpt-4o-realtime-preview-2024-12-17",
    "response": {...},      # ProviderResponse
    "duration_ms": 1234,
    "session_id": "sess_xyz"
}
```

### provider:error

**Emitted**: On any error

**Data**:
```python
{
    "provider": "openai-realtime",
    "error_type": "WebSocketConnectionError",
    "error_message": "Connection failed: ...",
    "context": {...}
}
```

## Mount Function

The provider exports a `mount()` function as the entry point:

```python
async def mount(
    coordinator: ModuleCoordinator,
    config: dict[str, Any] | None = None
) -> Callable[[], Awaitable[None]]:
    """
    Mount the provider module.

    Args:
        coordinator: Amplifier module coordinator
        config: Provider configuration

    Returns:
        Async cleanup function
    """
    config = config or {}

    # Extract configuration
    api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
    model = config.get("model", "gpt-4o-realtime-preview-2024-12-17")
    voice = config.get("voice", "alloy")

    # Initialize provider
    provider = OpenAIRealtimeProvider(
        api_key=api_key,
        config=config,
        coordinator=coordinator
    )

    # Mount to coordinator
    await coordinator.mount("providers", provider, name="openai-realtime")

    # Return cleanup function
    async def cleanup():
        await provider.session_manager.cleanup()

    return cleanup
```

**Configuration schema**:
```python
{
    "api_key": str,              # Required (or $OPENAI_API_KEY)
    "model": str,                # Optional, default shown above
    "voice": str,                # Optional, default "alloy"
    "temperature": float,        # Optional, default 0.7
    "max_tokens": int | None,    # Optional, no default
    "session_config": dict       # Optional, additional params
}
```

## Compatibility

### With Orchestrators

**Works with**:
- `loop-basic` - Turn-based conversation
- `loop-streaming` - Streaming transcript
- `loop-events` - Event-driven

**Interface**: Standard provider protocol, no orchestrator changes needed.

### With Tools

**Works with**: All existing Amplifier tools

**Integration**: Tool calls via standard `ToolCall` format, results sent via WebSocket.

### With Context Managers

**Works with**:
- `context-simple` - In-memory conversation
- `context-persistent` - File-backed conversation

**Interface**: Standard message format, no context manager changes needed.

## Version Compatibility

**Requires**:
- Python 3.11+
- amplifier-core (any version with Provider protocol)
- OpenAI API access (Realtime API preview)

**No breaking changes**: This provider works with existing Amplifier infrastructure unchanged.

## See Also

- [Architecture](ARCHITECTURE.md) - Component design
- [Audio Format](AUDIO_FORMAT.md) - Audio specifications
- [Session Lifecycle](SESSION_LIFECYCLE.md) - WebSocket management
- [Function Calling](FUNCTION_CALLING.md) - Tool integration details
