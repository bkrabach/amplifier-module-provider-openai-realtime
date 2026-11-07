import base64
import json
from typing import Any

import websockets

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
        self._completed_response_id: str | None = None

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
            message = json.loads(raw_message)
            if not isinstance(message, dict) or not isinstance(message.get("type"), str):
                raise ValueError("Invalid event envelope")
            return message
        except Exception:
            raise WebSocketConnectionError("Realtime receive failed or returned an invalid event") from None

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

        Accept current output_audio and legacy audio event names. Only the
        matching response.done ends a turn; audio.done is not turn completion.
        Independently decode each base64 delta (padding may occur per chunk).

        Returns:
            dict: Response containing:
                - audio_data (bytes): Decoded PCM16 audio
                - transcript (str): Text transcript
                - full_response (dict): Complete OpenAI response

        Raises:
            WebSocketConnectionError: If receive fails
        """
        audio: dict[tuple[int, int], list[bytes]] = {}
        transcripts: dict[tuple[int, int], str] = {}
        audio_done: set[tuple[int, int]] = set()
        transcript_done: set[tuple[int, int]] = set()
        seen: dict[str, dict[str, Any]] = {}
        response_id: str | None = None
        response_data: dict[str, Any] = {}

        while True:
            message = await self.receive()
            msg_type = message.get("type", "")
            if msg_type == "error":
                raise WebSocketConnectionError("OpenAI Realtime returned an error")
            # Other events (rate limits, item notifications, unknown extensions)
            # are not audio or terminal envelopes and must not fabricate output.
            canonical = msg_type.replace("response.output_audio", "response.audio", 1)
            if canonical not in {
                "response.created", "response.done", "response.audio.delta",
                "response.audio.done", "response.audio_transcript.delta",
                "response.audio_transcript.done",
            }:
                continue
            event_response = message.get("response", {})
            if canonical in {"response.created", "response.done"}:
                if not isinstance(event_response, dict):
                    raise WebSocketConnectionError("Invalid Realtime response envelope")
                incoming_id = event_response.get("id")
            else:
                incoming_id = message.get("response_id")
            if incoming_id is not None and (not isinstance(incoming_id, str) or not incoming_id):
                raise WebSocketConnectionError("Invalid Realtime response identity")
            if incoming_id and incoming_id == self._completed_response_id:
                continue  # A duplicate previous terminal/event cannot end the next turn.
            if response_id is not None and incoming_id != response_id:
                continue  # Never mix bytes or a terminal envelope from another response.
            if incoming_id is not None:
                response_id = incoming_id
            event_id = message.get("event_id")
            if event_id is not None:
                if not isinstance(event_id, str) or not event_id:
                    raise WebSocketConnectionError("Invalid Realtime event identity")
                if event_id in seen:
                    if seen[event_id] != message:
                        raise WebSocketConnectionError("Conflicting duplicate Realtime event")
                    continue
                seen[event_id] = message
            if canonical == "response.created":
                continue
            if canonical == "response.done":
                if event_response.get("status") not in (None, "completed"):
                    raise WebSocketConnectionError("Realtime response did not complete successfully")
                response_data = message
                self._completed_response_id = response_id
                break
            key = (message.get("output_index", 0), message.get("content_index", 0))
            if any(type(index) is not int or index < 0 for index in key):
                raise WebSocketConnectionError("Invalid Realtime content index")
            if canonical == "response.audio.delta":
                if key in audio_done:
                    raise WebSocketConnectionError("Realtime audio delta after audio.done")
                audio.setdefault(key, []).append(self._decode_audio(message.get("delta")))
            elif canonical == "response.audio.done":
                # Documented done events carry no audio bytes. Keep the legacy
                # full-audio extension only as a fallback when no deltas arrived.
                if key not in audio and message.get("audio"):
                    audio[key] = [self._decode_audio(message["audio"])]
                audio_done.add(key)
            elif canonical == "response.audio_transcript.delta":
                if key in transcript_done:
                    raise WebSocketConnectionError("Realtime transcript delta after transcript.done")
                delta = message.get("delta")
                if not isinstance(delta, str):
                    raise WebSocketConnectionError("Invalid Realtime transcript delta")
                transcripts[key] = transcripts.get(key, "") + delta
            elif canonical == "response.audio_transcript.done":
                transcript = message.get("transcript")
                if not isinstance(transcript, str):
                    raise WebSocketConnectionError("Invalid Realtime transcript")
                if key in transcript_done and transcripts[key] != transcript:
                    raise WebSocketConnectionError("Conflicting Realtime transcript.done")
                transcripts[key] = transcript
                transcript_done.add(key)

        audio_data = b"".join(chunk for key in sorted(audio) for chunk in audio[key])
        if len(audio_data) % 2:
            raise WebSocketConnectionError("Invalid PCM16 response (odd byte length)")
        return {
            "audio_data": audio_data,
            "transcript": "".join(transcripts[key] for key in sorted(transcripts)),
            "full_response": response_data,
        }

    @staticmethod
    def _decode_audio(value: Any) -> bytes:
        if not isinstance(value, str):
            raise WebSocketConnectionError("Invalid Realtime audio delta")
        try:
            return base64.b64decode(value, validate=True)
        except ValueError:
            raise WebSocketConnectionError("Invalid Realtime base64 audio") from None

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

        created_id = None
        conversation_created = False
        # At most: session.created, conversation.created, session.updated.
        # Neither creation event confirms that our configuration was applied.
        for _ in range(3):
            response = await self.receive()
            kind = response.get("type")
            if kind == "error":
                raise SessionInitializationError("OpenAI Realtime rejected session configuration")
            if kind == "conversation.created":
                conversation = response.get("conversation")
                event_id = response.get("event_id")
                if (not created_id or conversation_created or not isinstance(conversation, dict)
                        or not isinstance(event_id, str) or not event_id
                        or (conversation.get("id") is not None
                            and (not isinstance(conversation["id"], str) or not conversation["id"]))
                        or conversation.get("object") not in (None, "realtime.conversation")):
                    raise SessionInitializationError("Invalid Realtime conversation creation event")
                conversation_created = True
                continue
            if kind not in ("session.created", "session.updated"):
                raise SessionInitializationError("Unexpected event during session initialization")
            session = response.get("session")
            identity = session.get("id") if isinstance(session, dict) else None
            if not isinstance(identity, str) or not identity or (created_id and identity != created_id):
                raise SessionInitializationError("Invalid Realtime session identity")
            if kind == "session.created":
                created_id = identity
                continue  # Creation is not confirmation that our configuration was applied.
            self.session_id = identity
            return identity
        raise SessionInitializationError("Session initialization did not confirm configuration")

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
                self._completed_response_id = None
