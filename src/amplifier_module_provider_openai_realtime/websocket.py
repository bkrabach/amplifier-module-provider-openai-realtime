import json
from typing import Any

import websockets

from .audio_codec import decode_base64_audio
from .audio_codec import encode_base64_audio
from .exceptions import SessionInitializationError
from .exceptions import WebSocketConnectionError


class RealtimeWebSocket:
    """Handles OpenAI Realtime WebSocket protocol.

    Implements direct WebSocket communication with OpenAI's Realtime API.
    Manages connection lifecycle, message send/receive, and audio frame handling.

    Attributes:
        ws: WebSocket connection (None when not connected)
        session_id: OpenAI session ID (None until session initialized)
    """

    def __init__(self) -> None:
        """Initialize WebSocket handler with no active connection."""
        self.ws: Any = None
        self.session_id: str | None = None

    async def connect(self, api_key: str, model: str) -> None:
        """Establish WebSocket connection to OpenAI Realtime API.

        Args:
            api_key: OpenAI API key
            model: Model identifier (e.g., 'gpt-4o-realtime-preview-2024-12-17')

        Raises:
            WebSocketConnectionError: If connection fails
        """
        url = f"wss://api.openai.com/v1/realtime?model={model}"
        headers = {"Authorization": f"Bearer {api_key}", "OpenAI-Beta": "realtime=v1"}

        try:
            self.ws = await websockets.connect(url, additional_headers=headers)
        except Exception as e:
            raise WebSocketConnectionError(f"Failed to connect to {url}: {e}") from e

    def is_connected(self) -> bool:
        """Check if WebSocket connection is active.

        Returns:
            bool: True if connection exists
        """
        return self.ws is not None

    async def send(self, message: dict[str, Any]) -> None:
        """Send JSON message to WebSocket.

        Args:
            message: Message dict to send

        Raises:
            WebSocketConnectionError: If not connected
        """
        if not self.is_connected():
            raise WebSocketConnectionError("Cannot send: not connected")

        try:
            await self.ws.send(json.dumps(message))
        except Exception as e:
            raise WebSocketConnectionError(f"Send failed: {e}") from e

    async def receive(self) -> dict[str, Any]:
        """Receive JSON message from WebSocket.

        Returns:
            dict: Parsed JSON message

        Raises:
            WebSocketConnectionError: If not connected or receive fails
        """
        if not self.is_connected():
            raise WebSocketConnectionError("Cannot receive: not connected")

        try:
            raw_message = await self.ws.recv()
            return json.loads(raw_message)
        except Exception as e:
            raise WebSocketConnectionError(f"Receive failed: {e}") from e

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio input frame to OpenAI.

        Converts PCM16 bytes to base64 and sends via conversation.item.create
        followed by response.create to trigger model processing.

        Args:
            audio_data: PCM16 audio bytes

        Raises:
            WebSocketConnectionError: If send fails
        """
        audio_b64 = encode_base64_audio(audio_data)

        await self.send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_audio", "audio": audio_b64}],
                },
            }
        )

        await self.send({"type": "response.create"})

    async def receive_audio(self) -> dict[str, Any]:
        """Receive audio response from OpenAI.

        Collects audio.delta chunks until audio.done, then decodes and returns.

        Returns:
            dict: Response containing:
                - audio_data (bytes): Decoded PCM16 audio
                - transcript (str): Text transcript
                - full_response (dict): Complete OpenAI response

        Raises:
            WebSocketConnectionError: If receive fails
        """
        audio_chunks: list[str] = []
        transcript = ""
        response_data: dict[str, Any] = {}

        while True:
            message = await self.receive()
            msg_type = message.get("type", "")

            if msg_type == "response.audio.delta":
                audio_chunks.append(message.get("delta", ""))

            elif msg_type == "response.audio.done":
                full_audio = message.get("audio", "")
                if full_audio:
                    audio_chunks = [full_audio]

            elif msg_type == "response.audio_transcript.delta":
                transcript += message.get("delta", "")

            elif msg_type == "response.audio_transcript.done":
                transcript = message.get("transcript", transcript)

            elif msg_type == "response.done":
                response_data = message
                break

            elif msg_type == "error":
                error_msg = message.get("error", {})
                raise WebSocketConnectionError(f"OpenAI error: {error_msg.get('message', 'Unknown error')}")

        combined_audio_b64 = "".join(audio_chunks)
        audio_data = decode_base64_audio(combined_audio_b64) if combined_audio_b64 else b""

        return {"audio_data": audio_data, "transcript": transcript, "full_response": response_data}

    async def send_tool_result(self, tool_result: dict[str, Any]) -> None:
        """Send tool execution result to OpenAI.

        Args:
            tool_result: Tool result containing:
                - call_id (str): Tool call ID
                - output (str | dict): Tool result

        Raises:
            WebSocketConnectionError: If send fails
        """
        call_id = tool_result["call_id"]
        output = tool_result["output"]

        if not isinstance(output, str):
            output = json.dumps(output)

        await self.send(
            {
                "type": "conversation.item.create",
                "item": {"type": "function_call_output", "call_id": call_id, "output": output},
            }
        )

        await self.send({"type": "response.create"})

    async def initialize_session(self, instructions: str, voice: str, temperature: float) -> str:
        """Initialize session with configuration.

        Sends session.update with instructions, voice, and temperature settings.
        Waits for session.updated confirmation.

        Args:
            instructions: System instructions for the session
            voice: Voice identifier (e.g., 'alloy')
            temperature: Temperature for generation (0.0-1.0)

        Returns:
            str: Session ID from OpenAI

        Raises:
            SessionInitializationError: If initialization fails
        """
        await self.send(
            {
                "type": "session.update",
                "session": {
                    "instructions": instructions,
                    "voice": voice,
                    "temperature": temperature,
                },
            }
        )

        response = await self.receive()

        # Accept either session.created or session.updated
        if response.get("type") in ("session.created", "session.updated"):
            self.session_id = response.get("session", {}).get("id")
            if self.session_id:
                return self.session_id

        raise SessionInitializationError(f"Session initialization failed: {response}")

    async def close(self) -> None:
        """Close WebSocket connection gracefully.

        Sends close frame and waits for acknowledgment.
        Safe to call multiple times.
        """
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            finally:
                self.ws = None
                self.session_id = None
