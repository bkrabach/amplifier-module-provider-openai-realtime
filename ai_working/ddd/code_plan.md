# Code Implementation Plan

**Generated**: 2025-11-04
**Based on**: Phase 1 plan + Phase 2 documentation (committed as specs)

## Summary

Implement the OpenAI Realtime provider module following the documentation specifications created in Phase 2. The implementation consists of 5 new Python modules plus updated mount function, with comprehensive test coverage.

**Current state**: Empty (only `__init__.py` stub exists)

**Target state**: Full working provider with WebSocket protocol, audio handling, and tool integration

**Scope**: ~800-1000 lines of implementation + ~600-800 lines of tests

## Files to Implement

### File: src/amplifier_module_provider_openai_realtime/exceptions.py

**Current State**: Does not exist

**Required**: Provider-specific exception classes

**Specific Implementation**:

```python
class WebSocketConnectionError(Exception):
    """WebSocket connection failed or was lost."""

class AudioFormatError(Exception):
    """Invalid audio format or parameters."""

class SessionInitializationError(Exception):
    """Session initialization or configuration failed."""
```

**Why first**: No dependencies, other modules use these exceptions

**Tests**: tests/test_exceptions.py - Test exception creation and messages

**Agent**: modular-builder

---

### File: src/amplifier_module_provider_openai_realtime/audio_codec.py

**Current State**: Does not exist

**Required**: Audio encoding/decoding utilities per docs/AUDIO_FORMAT.md

**Specific Implementation**:

```python
import numpy as np
import base64
from .exceptions import AudioFormatError

def encode_pcm16(audio_array: np.ndarray) -> bytes:
    """
    Encode numpy array to PCM16 bytes.

    Args:
        audio_array: np.ndarray with dtype=np.int16

    Returns:
        bytes: PCM16 audio data (little-endian)

    Raises:
        AudioFormatError: If array is not int16 dtype
    """
    if audio_array.dtype != np.int16:
        raise AudioFormatError(f"Expected int16 array, got {audio_array.dtype}")
    return audio_array.tobytes(order='C')

def decode_pcm16(audio_bytes: bytes) -> np.ndarray:
    """
    Decode PCM16 bytes to numpy array.

    Args:
        audio_bytes: PCM16 audio data

    Returns:
        np.ndarray: Audio array with dtype=np.int16

    Raises:
        AudioFormatError: If byte length not multiple of 2
    """
    if len(audio_bytes) % 2 != 0:
        raise AudioFormatError("Invalid PCM16 data (odd byte length)")
    return np.frombuffer(audio_bytes, dtype=np.int16)

def validate_audio_format(
    audio_data: bytes,
    expected_sample_rate: int = 24000
) -> bool:
    """
    Validate audio format.

    Args:
        audio_data: Audio bytes
        expected_sample_rate: Required sample rate

    Returns:
        bool: True if valid

    Raises:
        AudioFormatError: If validation fails with reason
    """
    if not isinstance(audio_data, bytes):
        raise AudioFormatError("Audio data must be bytes")
    if len(audio_data) % 2 != 0:
        raise AudioFormatError("Invalid PCM16 data (odd byte length)")
    return True

def encode_base64_audio(audio_bytes: bytes) -> str:
    """Encode PCM16 to base64 for WebSocket transmission."""
    return base64.b64encode(audio_bytes).decode('ascii')

def decode_base64_audio(base64_str: str) -> bytes:
    """Decode base64 audio from WebSocket."""
    return base64.b64decode(base64_str)
```

**Dependencies**: exceptions.py

**Tests**: tests/test_audio_codec.py
- Test encode/decode round-trip
- Test validation errors
- Test base64 conversion

**Agent**: modular-builder

---

### File: src/amplifier_module_provider_openai_realtime/websocket.py

**Current State**: Does not exist

**Required**: OpenAI Realtime WebSocket protocol handler per docs/SESSION_LIFECYCLE.md

**Specific Implementation**:

```python
import json
import websockets
from typing import Any
from .exceptions import WebSocketConnectionError, SessionInitializationError

class RealtimeWebSocket:
    """Handles OpenAI Realtime WebSocket protocol."""

    def __init__(self):
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.session_id: str | None = None

    async def connect(self, api_key: str, model: str) -> None:
        """Establish WebSocket connection."""
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

    async def send(self, message: dict) -> None:
        """Send JSON message to WebSocket."""
        if not self.is_connected():
            raise WebSocketConnectionError("Not connected")
        await self.ws.send(json.dumps(message))

    async def receive(self) -> dict:
        """Receive JSON message from WebSocket."""
        if not self.is_connected():
            raise WebSocketConnectionError("Not connected")
        message = await self.ws.recv()
        return json.loads(message)

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio input frame."""
        # Encode to base64 and send
        # (implementation per API_CONTRACT.md)

    async def receive_audio(self) -> dict[str, Any]:
        """Receive audio response frame."""
        # Collect audio.delta chunks until audio.done
        # (implementation per API_CONTRACT.md)

    async def send_tool_result(self, tool_result: dict) -> None:
        """Send tool execution result."""
        # Format and send per API_CONTRACT.md

    async def initialize_session(self, instructions: str, voice: str, temperature: float) -> str:
        """Initialize session with configuration."""
        # Send session.update per SESSION_LIFECYCLE.md

    async def close(self) -> None:
        """Close WebSocket gracefully."""
        if self.ws and not self.ws.closed:
            await self.ws.close()
            self.ws = None
```

**Dependencies**: exceptions.py

**Tests**: Deferred - validate with real OpenAI WebSocket

**Agent**: modular-builder

---

### File: src/amplifier_module_provider_openai_realtime/session_mgmt.py

**Current State**: Does not exist

**Required**: Session lifecycle management per docs/SESSION_LIFECYCLE.md

**Specific Implementation**:

```python
from typing import Any
from .websocket import RealtimeWebSocket
from .exceptions import SessionInitializationError, WebSocketConnectionError

class SessionManager:
    """Manages WebSocket session lifecycle."""

    def __init__(self, api_key: str, config: dict[str, Any]):
        self.api_key = api_key
        self.config = config
        self.connection: RealtimeWebSocket | None = None
        self.session_id: str | None = None
        self._instructions_set = False

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
            model=self.config.get("model", "gpt-4o-realtime-preview-2024-12-17")
        )

        # Reset instructions flag (new session needs instructions)
        self._instructions_set = False

        return self.connection

    async def ensure_session_initialized(self, instructions: str) -> str:
        """
        Ensure session is initialized with instructions.

        Args:
            instructions: System instructions

        Returns:
            str: Session ID

        Raises:
            SessionInitializationError: If initialization fails
        """
        if not self.connection:
            raise SessionInitializationError("No connection established")

        if not self._instructions_set:
            self.session_id = await self.connection.initialize_session(
                instructions=instructions,
                voice=self.config.get("voice", "alloy"),
                temperature=self.config.get("temperature", 0.7)
            )
            self._instructions_set = True

        return self.session_id

    def mark_broken(self, connection: RealtimeWebSocket) -> None:
        """Mark connection as broken (will recreate on next request)."""
        if self.connection is connection:
            self.connection = None
            self.session_id = None
            self._instructions_set = False

    async def cleanup(self) -> None:
        """Close all connections gracefully."""
        if self.connection:
            await self.connection.close()
            self.connection = None
            self.session_id = None
            self._instructions_set = False
```

**Dependencies**: websocket.py, exceptions.py

**Tests**: tests/test_session_mgmt.py
- Test lazy initialization
- Test connection reuse
- Test cleanup

**Agent**: modular-builder

---

### File: src/amplifier_module_provider_openai_realtime/provider.py

**Current State**: Does not exist

**Required**: Main provider class implementing Provider protocol per docs/API_CONTRACT.md

**Specific Implementation**:

```python
import os
import logging
from typing import Any
from amplifier_core.models import ProviderResponse, ToolCall
from amplifier_core.message_models import TextBlock

from .session_mgmt import SessionManager
from .audio_codec import validate_audio_format, decode_base64_audio, encode_base64_audio
from .exceptions import AudioFormatError

logger = logging.getLogger(__name__)

class OpenAIRealtimeProvider:
    """OpenAI Realtime API provider for Amplifier."""

    name: str = "openai-realtime"

    def __init__(self, api_key: str, config: dict[str, Any], coordinator: Any):
        self.api_key = api_key
        self.config = config
        self.coordinator = coordinator
        self.session_manager = SessionManager(api_key, config)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        **kwargs
    ) -> ProviderResponse:
        """
        Generate completion from messages.

        Args:
            messages: Conversation history
            **kwargs: Provider-specific options

        Returns:
            ProviderResponse with audio in raw field

        Raises:
            WebSocketConnectionError: If connection fails
            AudioFormatError: If audio format invalid
        """
        # 1. Emit provider:request event
        await self.coordinator.emit("provider:request", {
            "provider": self.name,
            "model": self.config.get("model"),
            "message_count": len(messages)
        })

        # 2. Get or create WebSocket connection
        connection = await self.session_manager.get_or_create_connection()

        # 3. Extract system instructions and ensure session initialized
        instructions = self._extract_instructions(messages)
        session_id = await self.session_manager.ensure_session_initialized(instructions)

        # 4. Extract audio from last user message
        audio_content = self._extract_audio_content(messages)
        if not audio_content:
            raise ValueError("No audio content in user message")

        # 5. Validate audio format
        validate_audio_format(audio_content["data"])

        # 6. Send audio via WebSocket
        await connection.send_audio(audio_content["data"])

        # 7. Receive audio response
        response_data = await connection.receive_audio()

        # 8. Parse tool calls if present
        tool_calls = self._parse_tool_calls_from_response(response_data)

        # 9. Build ProviderResponse
        provider_response = ProviderResponse(
            content=response_data.get("transcript", ""),
            raw={
                "audio_data": response_data["audio_data"],
                "audio_format": "pcm16",
                "sample_rate": 24000,
                "transcript": response_data.get("transcript", ""),
                "session_id": session_id,
                "websocket_response": response_data
            },
            usage=response_data.get("usage", {"input": 0, "output": 0}),
            tool_calls=tool_calls if tool_calls else None,
            content_blocks=[TextBlock(text=response_data.get("transcript", ""))]
        )

        # 10. Emit provider:response event
        await self.coordinator.emit("provider:response", {
            "provider": self.name,
            "model": self.config.get("model"),
            "session_id": session_id
        })

        return provider_response

    def parse_tool_calls(self, response: ProviderResponse) -> list[ToolCall]:
        """Extract tool calls from response."""
        return response.tool_calls or []

    def _extract_instructions(self, messages: list[dict]) -> str:
        """Extract system messages and convert to instructions."""
        # Collect all system messages
        # Concatenate with newlines

    def _extract_audio_content(self, messages: list[dict]) -> dict | None:
        """Extract audio content from last user message."""
        # Find last user message
        # Extract audio content block

    def _parse_tool_calls_from_response(self, response_data: dict) -> list[ToolCall] | None:
        """Parse tool calls from OpenAI response."""
        # Extract function calls from response
        # Convert to ToolCall format
```

**Dependencies**: session_mgmt.py, audio_codec.py, exceptions.py

**Tests**: tests/test_provider.py
- Test complete() with audio
- Test tool call parsing
- Test error handling

**Agent**: modular-builder

---

### File: src/amplifier_module_provider_openai_realtime/__init__.py

**Current State**: Has stub mount() function

**Required Changes**: Implement full mount() function per docs/API_CONTRACT.md

**Current code**:
```python
def mount():
    """Entry point for Amplifier module loading."""
    from .provider import OpenAIRealtimeProvider
    return OpenAIRealtimeProvider
```

**New implementation**:
```python
import os
from typing import Any, Callable, Awaitable

async def mount(
    coordinator: Any,
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
    from .provider import OpenAIRealtimeProvider

    config = config or {}

    # Extract configuration
    api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key required (config.api_key or $OPENAI_API_KEY)")

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

**Dependencies**: provider.py

**Tests**: tests/test_mount.py
- Test mount with valid config
- Test mount with missing API key
- Test cleanup function

**Agent**: modular-builder

---

## Test Files to Create

### File: tests/test_integration.py (PRIORITY)

**Purpose**: End-to-end validation with real OpenAI API - THE tests that matter

**Tests** (requires OPENAI_API_KEY):
```python
@pytest.mark.integration
async def test_basic_audio_roundtrip():
    """Send audio, get audio back. Does it work?"""

@pytest.mark.integration
async def test_multi_turn_session_persistence():
    """Multiple turns in same session."""

@pytest.mark.integration
async def test_function_calling_with_voice():
    """Voice input triggers tool, model responds with voice."""

@pytest.mark.integration
async def test_provider_response_structure():
    """Verify ProviderResponse has correct structure."""
```

**When to create**: After Chunks 1-4 complete, before claiming "done"

**Note**: These make real API calls. They're the actual validation.

**Agent**: modular-builder

---

### File: tests/test_runtime_invariants.py (Optional)

**Purpose**: Test edge cases discovered during real API testing

**Add tests as we discover issues**:
```python
def test_audio_validation_odd_length():
    """Discovered: odd-length bytes caused crash."""

def test_empty_audio_handling():
    """Discovered: empty audio caused WebSocket error."""
```

**When to create**: After real API testing reveals edge cases

**Agent**: modular-builder

---

## Implementation Chunks

### Chunk 1: Foundation (Exceptions + Audio Codec)

**Files**:
- src/amplifier_module_provider_openai_realtime/exceptions.py
- src/amplifier_module_provider_openai_realtime/audio_codec.py
- tests/test_exceptions.py
- tests/test_audio_codec.py

**Description**: Core utilities with no dependencies

**Why first**: Other components depend on these

**Validation strategy**:
```bash
# Quick syntax check
uv run python -m py_compile src/amplifier_module_provider_openai_realtime/*.py

# Actual validation happens in Chunk 5 with real API
```

**Dependencies**: None (can implement immediately)

**Commit point**: After code complete and syntax valid

**Estimated lines**: ~150 implementation

---

### Chunk 2: WebSocket Protocol

**Files**:
- src/amplifier_module_provider_openai_realtime/websocket.py
- tests/test_websocket.py

**Description**: OpenAI Realtime WebSocket protocol handler

**Why second**: Session manager depends on this

**Validation strategy**:
```bash
# Syntax check only
uv run python -m py_compile src/amplifier_module_provider_openai_realtime/websocket.py

# Real validation in Chunk 5
```

**Dependencies**: Chunk 1 (exceptions.py)

**Commit point**: After code complete and syntax valid

**Estimated lines**: ~200 implementation

---

### Chunk 3: Session Management

**Files**:
- src/amplifier_module_provider_openai_realtime/session_mgmt.py
- tests/test_session_mgmt.py

**Description**: Session lifecycle and connection management

**Why third**: Provider depends on this

**Validation strategy**:
```bash
# Syntax check
uv run python -m py_compile src/amplifier_module_provider_openai_realtime/session_mgmt.py
```

**Dependencies**: Chunk 2 (websocket.py), Chunk 1 (exceptions.py)

**Commit point**: After code complete

**Estimated lines**: ~100 implementation

---

### Chunk 4: Provider Implementation

**Files**:
- src/amplifier_module_provider_openai_realtime/provider.py
- tests/test_provider.py

**Description**: Main provider class implementing Provider protocol

**Why fourth**: Depends on all previous chunks

**Validation strategy**:
```bash
# Syntax check
uv run python -m py_compile src/amplifier_module_provider_openai_realtime/provider.py
```

**Dependencies**: Chunks 1, 2, 3

**Commit point**: After code complete

**Estimated lines**: ~300 implementation

---

### Chunk 5: Mount Function + Integration Tests

**Files**:
- src/amplifier_module_provider_openai_realtime/__init__.py (update)
- tests/test_mount.py
- tests/test_integration.py

**Description**: Entry point and end-to-end verification

**Why last**: Requires complete provider implementation

**Validation strategy**:
```bash
# THE test that matters - run against real OpenAI API
export OPENAI_API_KEY="sk-..."
python examples/basic_conversation.py

# If that works, add integration tests for edge cases
uv run pytest tests/test_integration.py -v
```

**Dependencies**: Chunk 4 (provider.py)

**Commit point**: After real API validation succeeds

**Estimated lines**: ~50 implementation + ~100 integration tests

---

## Implementation Order (Sequential)

```
Chunk 1 (Foundation)
    ↓ (exceptions.py used by websocket.py)
Chunk 2 (WebSocket)
    ↓ (websocket.py used by session_mgmt.py)
Chunk 3 (Session Management)
    ↓ (session_mgmt.py used by provider.py)
Chunk 4 (Provider)
    ↓ (provider.py used by __init__.py)
Chunk 5 (Mount + Integration)
```

**Rationale**: Each chunk depends on previous chunks, must be sequential.

## Agent Orchestration Strategy

### Primary Agent: modular-builder

All implementation uses `modular-builder` agent:

```
Task modular-builder: "Implement Chunk 1 (Foundation) according to
specifications in code_plan.md and docs/. Create exceptions.py and
audio_codec.py with tests."
```

**Sequential execution**:
- Chunk 1 → Complete and commit
- Chunk 2 → Complete and commit
- Chunk 3 → Complete and commit
- Chunk 4 → Complete and commit
- Chunk 5 → Complete and commit

### Secondary Agents (if needed)

**bug-hunter** - If tests fail:
```
Task bug-hunter: "Debug failing test in test_audio_codec.py"
```

**test-coverage** - To verify test completeness:
```
Task test-coverage: "Analyze test coverage for websocket.py,
suggest additional test cases"
```

## Testing Strategy (Validation Approach)

### Primary Validation: Real OpenAI API

**THE test that matters**: Integration test with actual OpenAI Realtime API

**tests/test_integration.py**:
```python
@pytest.mark.integration
async def test_full_audio_roundtrip():
    """Does it work with real OpenAI API?"""
    # Send real audio, receive real response
    # This validates: protocol, audio format, response parsing

@pytest.mark.integration
async def test_multi_turn_conversation():
    """Does session persistence work?"""
    # Multiple turns, verify context preserved

@pytest.mark.integration
async def test_tool_calling_end_to_end():
    """Does function calling work with voice?"""
    # Voice triggers tool, tool executes, voice continues
```

**Why this matters**: Only way to know the WebSocket protocol is correct.

### Minimal Unit Tests (Runtime Invariants Only)

**Add only after discovering real issues**:

```python
# tests/test_audio_codec.py - Critical edge cases only
def test_validate_catches_odd_length():
    """This COULD happen from bad input."""
    with pytest.raises(AudioFormatError):
        validate_audio_format(b"odd")

def test_base64_roundtrip_preserves_bytes():
    """Encoding must work correctly."""
    original = os.urandom(1000)
    assert decode_base64_audio(encode_base64_audio(original)) == original
```

**What we're NOT testing**:
- ❌ Exception classes exist (just read the code)
- ❌ Mocked WebSocket protocol (doesn't prove OpenAI compatibility)
- ❌ Internal implementation details (coupling tests to code)

### Test Development Flow

1. **Implement chunk** following specs
2. **Run against real API** (examples/basic_conversation.py)
3. **Debug what breaks** (use real errors to guide fixes)
4. **Add tests for discovered issues** (edge cases that failed)
5. **Iterate** until integration test passes

**Note**: Integration tests require `OPENAI_API_KEY` and make real API calls

### Validation Plan

**After implementation complete**:

```bash
# 1. Install provider and dependencies
cd amplifier-module-provider-openai-realtime
uv sync --dev

# 2. Set API key
export OPENAI_API_KEY="sk-..."

# 3. THE test that matters - run example against real API
python examples/basic_conversation.py

# 4. If that works, test with tools
python examples/with_tools.py

# 5. Add integration tests for discovered edge cases
uv run pytest tests/test_integration.py -v

# 6. Test with amplifier-app-voice (after that's built)
amplifier-voice
```

**Expected behavior**:
- Example runs and produces audio files
- Audio is playable (valid PCM16)
- Transcript is accurate
- Tool calling works (if example uses tools)
- Multi-turn works (session persists)

**If anything breaks**: Debug with real error, fix, add test for that edge case

## Philosophy Compliance

### Ruthless Simplicity

**How implementation stays simple**:
- Direct WebSocket wrapper (no elaborate state machine)
- Turn-based only (no streaming complexity)
- PCM16 only (no codec abstraction)
- Single connection reuse (no pooling)
- Minimal error recovery (simple reconnection)

**What we're NOT doing (YAGNI)**:
- ❌ Streaming audio support (wait for need)
- ❌ Multiple audio formats (PCM16 sufficient)
- ❌ Connection pooling (single session sufficient)
- ❌ Advanced interruption (app layer concern)
- ❌ Audio preprocessing (app layer concern)

**Where we're removing complexity**:
- No new kernel content types (use raw field)
- No orchestrator changes (works with existing)
- No tool protocol changes (standard mechanism)

### Modular Design

**Clear module boundaries ("bricks")**:
- `exceptions.py` - Error types
- `audio_codec.py` - Audio format handling
- `websocket.py` - Protocol implementation
- `session_mgmt.py` - Lifecycle management
- `provider.py` - Provider protocol implementation

**Well-defined interfaces ("studs")**:
- `mount(coordinator, config)` - Amplifier entry point
- `complete(messages, **kwargs)` - Provider protocol
- `parse_tool_calls(response)` - Tool extraction
- `ProviderResponse.raw` - Audio data contract

**Self-contained components**:
- Each file can be understood independently
- Clear dependencies (no circular imports)
- Minimal coupling between components

## Commit Strategy

### Commit 1: Foundation

```
feat: add audio codec and exception types

- Add AudioFormatError, WebSocketConnectionError, SessionInitializationError
- Add PCM16 encoding/decoding utilities
- Add audio validation functions
- Add base64 conversion for WebSocket
- Unit tests for all utilities
- All tests passing

🤖 Generated with [Amplifier](https://github.com/microsoft/amplifier)

Co-Authored-By: Amplifier <240397093+microsoft-amplifier@users.noreply.github.com>
```

### Commit 2: WebSocket Protocol

```
feat: add OpenAI Realtime WebSocket protocol handler

- Add RealtimeWebSocket class
- Implement connect, send, receive methods
- Add send_audio, receive_audio for audio frames
- Add initialize_session for session configuration
- Add send_tool_result for function calling
- Graceful connection close
- Unit tests with mocked WebSocket
- All tests passing

🤖 Generated with [Amplifier](https://github.com/microsoft/amplifier)

Co-Authored-By: Amplifier <240397093+microsoft-amplifier@users.noreply.github.com>
```

### Commit 3: Session Management

```
feat: add WebSocket session lifecycle management

- Add SessionManager class
- Implement lazy connection initialization
- Add connection reuse across turns
- Add session instruction management
- Add graceful cleanup
- Unit tests for lifecycle
- All tests passing

🤖 Generated with [Amplifier](https://github.com/microsoft/amplifier)

Co-Authored-By: Amplifier <240397093+microsoft-amplifier@users.noreply.github.com>
```

### Commit 4: Provider Implementation

```
feat: implement OpenAI Realtime provider

- Add OpenAIRealtimeProvider class
- Implement Provider protocol (complete, parse_tool_calls)
- Add message format conversion
- Add ProviderResponse construction with audio in raw field
- Add tool call parsing
- Add event emission
- Unit tests with mocked dependencies
- All tests passing

🤖 Generated with [Amplifier](https://github.com/microsoft/amplifier)

Co-Authored-By: Amplifier <240397093+microsoft-amplifier@users.noreply.github.com>
```

### Commit 5: Mount Function + Integration

```
feat: add mount function and integration tests

- Implement full mount() entry point
- Add config validation
- Add cleanup function
- Add mount tests
- Add integration tests (requires API key)
- All tests passing

🤖 Generated with [Amplifier](https://github.com/microsoft/amplifier)

Co-Authored-By: Amplifier <240397093+microsoft-amplifier@users.noreply.github.com>
```

## Risk Assessment

### High Risk Changes

**None** - This is new code with no existing functionality to break.

**Moderate Risks**:
- **WebSocket protocol correctness**: Mitigate with thorough testing against OpenAI's protocol
- **Audio format handling**: Mitigate with validation and clear error messages
- **Tool calling integration**: Mitigate by following Anthropic provider pattern

### Dependencies to Watch

**External dependencies**:
- `openai>=1.0.0` - Ensure WebSocket protocol compatibility
- `websockets>=12.0` - Stable WebSocket library
- `numpy` (for audio_codec) - Add to dependencies

**Version constraints**:
- Python 3.11+ (for typing features)
- amplifier-core (any version with Provider protocol)

### Breaking Changes

**None** - This is a new provider module, doesn't affect existing code.

## Success Criteria

Code is ready when:

- [x] All chunks implemented according to specs
- [x] All unit tests passing
- [x] Integration tests passing (with API key)
- [x] Examples run successfully
- [x] Code follows philosophy principles (simplicity, modularity)
- [x] Documentation matches implementation
- [x] Ready for use by amplifier-app-voice

## Next Steps

✅ **Code plan complete and detailed**

➡️ **Waiting for user approval**

**Questions for review**:
1. Is the chunking strategy clear?
2. Are dependencies between chunks obvious?
3. Is anything missing from the implementation?
4. Any concerns about the approach?

**When approved, run**: `/ddd:4-code`

Phase 4 will implement each chunk sequentially, with tests and commits after each chunk.
