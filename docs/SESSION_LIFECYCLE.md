# Session Lifecycle

This document describes the WebSocket connection management for the OpenAI Realtime provider.

## Overview

The provider maintains a **persistent WebSocket connection** across multiple conversation turns. This session-based model:

- Reduces connection overhead (no reconnection per request)
- Preserves conversation context automatically
- Aligns with OpenAI's Realtime API design
- Simplifies state management

## Session States

```
┌─────────────┐
│ UNCONNECTED │  Initial state, no WebSocket yet
└──────┬──────┘
       │ first complete() call
       ▼
┌─────────────┐
│ CONNECTING  │  WebSocket handshake in progress
└──────┬──────┘
       │ handshake success
       ▼
┌─────────────┐
│  CONNECTED  │  Session active, can send/receive
└──────┬──────┘
       │ multiple turns (reuse connection)
       │
       │ session close or error
       ▼
┌─────────────┐
│    CLOSED   │  WebSocket terminated
└─────────────┘
```

## Lifecycle Phases

### Phase 1: Initialization

**When**: Provider module mounted by Amplifier kernel

**What happens**:

```python
# 1. mount() called with config
async def mount(coordinator, config):
    provider = OpenAIRealtimeProvider(
        api_key=config["api_key"],
        model=config["model"],
        voice=config["voice"],
        coordinator=coordinator
    )

    # 2. SessionManager created (no connection yet)
    provider.session_manager = SessionManager(
        api_key=api_key,
        config=config
    )

    # 3. Provider registered
    await coordinator.mount("providers", provider, name="openai-realtime")

    # 4. Cleanup function returned
    return provider.cleanup
```

**State**: `UNCONNECTED`

**Notes**:
- No WebSocket connection established yet
- Lazy initialization (connect on first use)
- Config validated but not applied

### Phase 2: First Request (Connection Establishment)

**When**: First `complete()` call

**What happens**:

```python
# 1. complete() called with audio
async def complete(self, messages, **kwargs):
    # 2. SessionManager checks for existing connection
    connection = await self.session_manager.get_or_create_connection()
    # → No connection exists, create new one

    # 3. WebSocket connection established
    await connection.connect(
        api_key=self.api_key,
        model=self.model
    )
    # → WSS handshake with OpenAI

    # 4. Session initialized with instructions
    instructions = self._extract_instructions(messages)
    await connection.initialize_session(instructions)
    # → session.update sent with instructions

    # 5. Audio sent and response received
    await connection.send_audio(audio_data)
    response = await connection.receive_audio()

    # 6. Connection kept alive for next turn
```

**State transition**: `UNCONNECTED → CONNECTING → CONNECTED`

**Events emitted**:
- `provider:request` - Before WebSocket send
- `provider:response` - After successful response

### Phase 3: Subsequent Requests (Connection Reuse)

**When**: Additional `complete()` calls in same session

**What happens**:

```python
# 1. complete() called again
async def complete(self, messages, **kwargs):
    # 2. SessionManager finds existing connection
    connection = await self.session_manager.get_or_create_connection()
    # → Reuses existing WebSocket

    # 3. No reconnection needed
    # (skip connect and initialize_session)

    # 4. Audio sent directly
    await connection.send_audio(audio_data)
    response = await connection.receive_audio()

    # 5. Connection remains open
```

**State**: `CONNECTED` (no change)

**Benefits**:
- Faster (no handshake overhead)
- Context preserved (OpenAI remembers conversation)
- Simpler (no reconnection logic needed)

### Phase 4: Tool Call Flow

**When**: Model decides to call a tool

**What happens**:

```python
# 1. Model response includes function call
response = await connection.receive_audio()
# → Contains function_call event

# 2. Provider parses tool call
tool_calls = self.parse_tool_calls(response)

# 3. Orchestrator executes tool (via Amplifier)
tool_result = await orchestrator.execute_tool(tool_calls[0])

# 4. Result sent back via WebSocket
await connection.send_tool_result({
    "call_id": tool_calls[0].id,
    "output": tool_result
})

# 5. Model continues with audio response
final_response = await connection.receive_audio()
```

**State**: `CONNECTED` (throughout)

**Notes**:
- WebSocket remains open during tool execution
- Multiple tool calls handled sequentially
- Connection persists after tool completion

### Phase 5: Error Recovery

**When**: WebSocket error or network issue

**What happens**:

```python
# 1. Connection error detected
try:
    response = await connection.receive_audio()
except WebSocketConnectionError as e:
    # 2. Connection marked as broken
    self.session_manager.mark_broken(connection)

    # 3. Error logged and emitted
    logger.error(f"WebSocket error: {e}")
    await self.coordinator.emit("provider:error", {
        "error_type": "WebSocketConnectionError",
        "error_message": str(e)
    })

    # 4. Error propagated to caller
    raise
```

**State transition**: `CONNECTED → CLOSED`

**Recovery**:
- Next `complete()` call creates new connection
- Automatic reconnection on subsequent request
- No manual intervention needed

### Phase 6: Graceful Shutdown

**When**: Session closed by application

**What happens**:

```python
# 1. Application closes session
async with AmplifierSession(config=config) as session:
    # ... use session ...
    pass  # Context exit

# 2. Cleanup function invoked
await provider.cleanup()

# 3. SessionManager closes WebSocket
await self.session_manager.cleanup()
    # → Sends close frame
    # → Waits for acknowledgment
    # → Closes socket

# 4. Resources released
# - WebSocket closed
# - Buffers cleared
# - Event listeners removed
```

**State transition**: `CONNECTED → CLOSED`

**Notes**:
- Graceful close (sends close frame)
- No data loss (waits for acknowledgment)
- Clean resource cleanup

## Session Management

### SessionManager Class

```python
class SessionManager:
    """Manages WebSocket session lifecycle."""

    def __init__(self, api_key: str, config: dict):
        self.api_key = api_key
        self.config = config
        self.connection: RealtimeWebSocket | None = None
        self.session_id: str | None = None

    async def get_or_create_connection(self) -> RealtimeWebSocket:
        """
        Get existing connection or create new one.

        Returns:
            RealtimeWebSocket: Active connection

        Raises:
            WebSocketConnectionError: If connection fails
        """
        if self.connection and self.connection.is_connected():
            return self.connection

        # Create new connection
        self.connection = RealtimeWebSocket()
        await self.connection.connect(
            api_key=self.api_key,
            model=self.config["model"]
        )

        return self.connection

    async def initialize_session(self, instructions: str) -> str:
        """
        Initialize session with instructions.

        Args:
            instructions: System instructions for session

        Returns:
            str: Session ID

        Raises:
            SessionInitializationError: If initialization fails
        """
        if not self.connection:
            raise SessionInitializationError("No connection established")

        # Send session.update
        response = await self.connection.send({
            "type": "session.update",
            "session": {
                "instructions": instructions,
                "voice": self.config["voice"],
                "temperature": self.config.get("temperature", 0.7)
            }
        })

        self.session_id = response["session"]["id"]
        return self.session_id

    async def cleanup(self) -> None:
        """Close connection gracefully."""
        if self.connection:
            await self.connection.close()
            self.connection = None
            self.session_id = None
```

### RealtimeWebSocket Class

```python
class RealtimeWebSocket:
    """Handles OpenAI Realtime WebSocket protocol."""

    def __init__(self):
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.session_id: str | None = None

    async def connect(self, api_key: str, model: str) -> None:
        """
        Establish WebSocket connection.

        Args:
            api_key: OpenAI API key
            model: Model identifier

        Raises:
            WebSocketConnectionError: If connection fails
        """
        url = f"wss://api.openai.com/v1/realtime?model={model}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "realtime=v1"
        }

        try:
            self.ws = await websockets.connect(url, extra_headers=headers)
        except Exception as e:
            raise WebSocketConnectionError(f"Failed to connect: {e}")

    def is_connected(self) -> bool:
        """Check if connection is active."""
        return self.ws is not None and not self.ws.closed

    async def send(self, message: dict) -> dict:
        """
        Send message and wait for response.

        Args:
            message: Message to send

        Returns:
            dict: Response message

        Raises:
            WebSocketConnectionError: If send fails
        """
        if not self.is_connected():
            raise WebSocketConnectionError("Not connected")

        await self.ws.send(json.dumps(message))
        response = await self.ws.recv()
        return json.loads(response)

    async def close(self) -> None:
        """Close connection gracefully."""
        if self.ws and not self.ws.closed:
            await self.ws.close()
            self.ws = None
```

## Connection Parameters

### WebSocket URL

```
wss://api.openai.com/v1/realtime?model={model}
```

**Parameters**:
- `model` - Model identifier (e.g., `gpt-4o-realtime-preview-2024-12-17`)

### Headers

```python
{
    "Authorization": "Bearer {api_key}",
    "OpenAI-Beta": "realtime=v1"
}
```

**Required**:
- `Authorization` - Bearer token with API key
- `OpenAI-Beta` - Beta feature flag

### Session Configuration

Sent via `session.update` after connection:

```json
{
    "type": "session.update",
    "session": {
        "instructions": "You are a helpful assistant.",
        "voice": "alloy",
        "temperature": 0.7,
        "max_response_output_tokens": null
    }
}
```

## Message Flow

### Sending Audio

```
Provider → WebSocket:
{
    "type": "conversation.item.create",
    "item": {
        "type": "message",
        "role": "user",
        "content": [
            {
                "type": "input_audio",
                "audio": "base64_encoded_pcm16"
            }
        ]
    }
}

{
    "type": "response.create"
}
```

### Receiving Audio

```
WebSocket → Provider:
{
    "type": "response.audio.delta",
    "delta": "base64_audio_chunk"
}

{
    "type": "response.audio.done",
    "audio": "full_base64_audio",
    "transcript": "Text version"
}
```

### Tool Call Flow

```
WebSocket → Provider:
{
    "type": "response.function_call_arguments.done",
    "call_id": "call_abc123",
    "name": "get_weather",
    "arguments": "{\"location\":\"SF\"}"
}

Provider → WebSocket:
{
    "type": "conversation.item.create",
    "item": {
        "type": "function_call_output",
        "call_id": "call_abc123",
        "output": "{\"temperature\":72}"
    }
}

{
    "type": "response.create"
}

WebSocket → Provider:
{
    "type": "response.audio.done",
    "audio": "...",
    "transcript": "It's 72 degrees in San Francisco."
}
```

## Error Handling

### Connection Errors

**Causes**:
- Invalid API key
- Network issues
- OpenAI service downtime
- Invalid model specified

**Handling**:
```python
try:
    await connection.connect(api_key, model)
except WebSocketConnectionError as e:
    logger.error(f"Connection failed: {e}")
    # Propagate to caller
    raise
```

**Recovery**:
- Automatic on next request
- No manual intervention needed

### Session Initialization Errors

**Causes**:
- Invalid instructions
- Unsupported voice
- Configuration errors

**Handling**:
```python
try:
    session_id = await connection.initialize_session(instructions)
except SessionInitializationError as e:
    logger.error(f"Session init failed: {e}")
    # Close broken connection
    await connection.close()
    raise
```

**Recovery**:
- Fix configuration
- Retry with corrected config

### Mid-Conversation Errors

**Causes**:
- Network interruption
- WebSocket timeout
- Server error

**Handling**:
```python
try:
    response = await connection.receive_audio()
except WebSocketConnectionError as e:
    logger.error(f"Receive error: {e}")
    # Mark connection broken
    self.session_manager.mark_broken(connection)
    raise
```

**Recovery**:
- Next request creates new connection
- Conversation context lost (fresh session)

## Performance Characteristics

### Latency

**First request** (cold start):
- Connection: ~200-300ms (WebSocket handshake)
- Session init: ~100ms (session.update)
- Audio processing: ~500-1000ms (OpenAI)
- **Total: ~800-1400ms**

**Subsequent requests** (warm):
- Audio processing: ~500-1000ms (OpenAI only)
- **Total: ~500-1000ms** (no connection overhead)

**Improvement**: 40-60% faster on subsequent requests

### Resource Usage

**Memory**:
- WebSocket: ~1MB per connection
- Audio buffers: ~50KB per turn
- **Total: ~1-2MB** per active session

**CPU**:
- Minimal (no audio encoding/decoding)
- Network I/O dominant

**Network**:
- 384 kbps (48 KB/s) sustained during audio
- Idle: minimal keepalive traffic

## Best Practices

### 1. Reuse Connections

**GOOD**:
```python
async with AmplifierSession(config=config) as session:
    # Multiple turns, same session
    response1 = await session.execute(audio1)
    response2 = await session.execute(audio2)
    response3 = await session.execute(audio3)
    # WebSocket reused across all turns
```

**BAD**:
```python
# Creating new session per turn
for audio in audios:
    async with AmplifierSession(config=config) as session:
        response = await session.execute(audio)
    # Reconnects every time! Slow!
```

### 2. Handle Errors Gracefully

```python
try:
    response = await session.execute(audio)
except WebSocketConnectionError as e:
    # Log and inform user
    logger.error(f"Connection error: {e}")
    print("Connection lost, please try again")
    # Automatic reconnection on retry
```

### 3. Clean Up Resources

```python
async with AmplifierSession(config=config) as session:
    try:
        response = await session.execute(audio)
    finally:
        # Cleanup happens automatically on context exit
        pass
```

### 4. Monitor Session Health

```python
# Check connection status
if session_manager.connection and session_manager.connection.is_connected():
    print("Session active")
else:
    print("Session disconnected")
```

## Troubleshooting

### Issue: "Not connected" error on first request

**Cause**: Connection establishment failed.

**Debug**:
```python
# Check API key
print(f"API key: {api_key[:10]}...")

# Check network
import websockets
try:
    await websockets.connect("wss://api.openai.com")
    print("Network OK")
except Exception as e:
    print(f"Network error: {e}")
```

### Issue: Connection drops mid-conversation

**Cause**: Network interruption or timeout.

**Solution**: Automatic reconnection on next request.

**Monitoring**:
```python
# Log connection events
await coordinator.emit("provider:connection_lost", {
    "session_id": session_id,
    "duration": connection_duration
})
```

### Issue: Memory usage grows over time

**Cause**: Audio buffers not released.

**Solution**: Ensure cleanup on session close:
```python
async def cleanup(self):
    if self.connection:
        await self.connection.close()
        self.connection = None  # Release reference
```

## See Also

- [Architecture](ARCHITECTURE.md) - Module design overview
- [Audio Format](AUDIO_FORMAT.md) - Audio specifications
- [API Contract](API_CONTRACT.md) - Provider protocol
- [Function Calling](FUNCTION_CALLING.md) - Tool integration
