from typing import Any

from .exceptions import SessionInitializationError
from .websocket import RealtimeWebSocket


class SessionManager:
    """Manages WebSocket session lifecycle.

    Implements lazy connection initialization and reuse across multiple turns.
    Maintains session state and handles graceful cleanup.

    Lifecycle per docs/SESSION_LIFECYCLE.md:
    - Phase 1: Initialize with no connection (lazy)
    - Phase 2: First request creates WebSocket and initializes session
    - Phase 3: Subsequent requests reuse existing connection
    - Phase 5: Mark broken on errors (recreate on next request)
    - Phase 6: Cleanup closes WebSocket gracefully

    Attributes:
        api_key: OpenAI API key for authentication
        config: Provider configuration (model, voice, temperature)
        connection: Active WebSocket connection (None if not connected)
        session_id: OpenAI session ID (None until session initialized)
        _instructions_set: Whether session has been configured with instructions
    """

    def __init__(self: "SessionManager", api_key: str, config: dict[str, Any]) -> None:
        """Initialize session manager with no active connection.

        Args:
            api_key: OpenAI API key
            config: Provider configuration dict containing:
                - model: Model identifier
                - voice: Voice parameter
                - temperature: Generation temperature
        """
        self.api_key = api_key
        self.config = config
        self.connection: RealtimeWebSocket | None = None
        self.session_id: str | None = None
        self._instructions_set = False

    async def get_or_create_connection(self: "SessionManager") -> RealtimeWebSocket:
        """Get existing connection or create new one.

        Implements lazy initialization: connection created on first use.
        Reuses connection if already established and connected.

        Returns:
            RealtimeWebSocket: Active connection ready for use

        Raises:
            WebSocketConnectionError: If connection establishment fails
        """
        if self.connection and self.connection.is_connected():
            return self.connection

        self.connection = RealtimeWebSocket()
        await self.connection.connect(
            api_key=self.api_key, model=self.config.get("model", "gpt-4o-realtime-preview-2024-12-17")
        )

        self._instructions_set = False

        return self.connection

    async def ensure_session_initialized(self: "SessionManager", instructions: str) -> str:
        """Ensure session is initialized with instructions.

        Instructions are set once per connection. Subsequent calls with same
        connection are no-ops (instructions persist for session).

        Args:
            instructions: System instructions for the session

        Returns:
            str: Session ID from OpenAI

        Raises:
            SessionInitializationError: If no connection or initialization fails
        """
        if not self.connection:
            raise SessionInitializationError("No connection established")

        if not self._instructions_set:
            self.session_id = await self.connection.initialize_session(
                instructions=instructions,
                voice=self.config.get("voice", "alloy"),
                temperature=self.config.get("temperature", 0.7),
            )
            self._instructions_set = True

        if not self.session_id:
            raise SessionInitializationError("Session ID not set after initialization")

        return self.session_id

    def mark_broken(self: "SessionManager", connection: RealtimeWebSocket) -> None:
        """Mark connection as broken (will recreate on next request).

        Called when connection errors are detected. Clears internal state so
        next request creates a fresh connection.

        Args:
            connection: The connection instance to mark as broken
        """
        if self.connection is connection:
            self.connection = None
            self.session_id = None
            self._instructions_set = False

    async def cleanup(self: "SessionManager") -> None:
        """Close all connections gracefully.

        Closes WebSocket with proper close frame and waits for acknowledgment.
        Clears internal state. Safe to call multiple times.
        """
        if self.connection:
            await self.connection.close()
            self.connection = None
            self.session_id = None
            self._instructions_set = False
