"""OpenAI Realtime provider implementation."""

import json
import logging
from typing import TYPE_CHECKING
from typing import Any

from .audio_codec import validate_audio_format
from .exceptions import AudioFormatError
from .exceptions import WebSocketConnectionError
from .session_mgmt import SessionManager

if TYPE_CHECKING:
    from amplifier_core.models import ProviderResponse
    from amplifier_core.models import ToolCall

logger = logging.getLogger(__name__)


class OpenAIRealtimeProvider:
    """OpenAI Realtime API provider implementing Amplifier's Provider protocol.

    Implements complete() method to send audio/text messages and receive audio responses.
    Supports tool calling through WebSocket protocol.

    Per docs/API_CONTRACT.md:
    - System messages → Session instructions (set once)
    - User audio → WebSocket send_audio()
    - Response → ProviderResponse with audio in raw field
    - Tool calls → Parsed from WebSocket response

    Attributes:
        name: Provider identifier ("openai-realtime")
        session_manager: Manages WebSocket lifecycle
        coordinator: Module coordinator for event emission
    """

    name: str = "openai-realtime"

    def __init__(self: "OpenAIRealtimeProvider", api_key: str, config: dict[str, Any], coordinator: Any) -> None:
        """Initialize provider with configuration.

        Args:
            api_key: OpenAI API key
            config: Provider configuration dict
            coordinator: Amplifier module coordinator
        """
        self.session_manager = SessionManager(api_key, config)
        self.coordinator = coordinator
        self.config = config

    async def complete(
        self: "OpenAIRealtimeProvider", messages: list[dict[str, Any]], **kwargs: Any
    ) -> "ProviderResponse":
        """Generate completion from messages.

        Per docs/API_CONTRACT.md:
        1. Extract system messages → session instructions
        2. Extract audio from last user message
        3. Send audio via WebSocket
        4. Receive audio response
        5. Parse tool calls if present
        6. Build ProviderResponse with audio in raw field

        Args:
            messages: Message list in Amplifier format
            **kwargs: Additional parameters (unused)

        Returns:
            ProviderResponse: Response with audio data in raw field

        Raises:
            AudioFormatError: Invalid audio format
            WebSocketConnectionError: Connection failed
        """
        from amplifier_core.message_models import TextBlock
        from amplifier_core.models import ProviderResponse

        instructions = self._extract_instructions(messages)
        connection = None

        try:
            self.coordinator.emit(
                "provider:request",
                {
                    "provider": self.name,
                    "model": self.config.get("model", "gpt-4o-realtime-preview-2024-12-17"),
                    "messages": messages,
                },
            )

            connection = await self.session_manager.get_or_create_connection()

            await self.session_manager.ensure_session_initialized(instructions)

            audio_data = self._extract_audio(messages)

            validate_audio_format(audio_data)

            await connection.send_audio(audio_data)

            response = await connection.receive_audio()

            tool_calls = self._parse_tool_calls_from_ws_response(response["full_response"])

            provider_response = ProviderResponse(
                content=response["transcript"],
                raw={
                    "audio_data": response["audio_data"],
                    "audio_format": "pcm16",
                    "sample_rate": 24000,
                    "transcript": response["transcript"],
                    "session_id": self.session_manager.session_id or "",
                    "websocket_response": response["full_response"],
                },
                usage=self._extract_usage(response["full_response"]),
                tool_calls=tool_calls if tool_calls else None,
                content_blocks=[TextBlock(text=response["transcript"])],
            )

            self.coordinator.emit(
                "provider:response",
                {
                    "provider": self.name,
                    "model": self.config.get("model", "gpt-4o-realtime-preview-2024-12-17"),
                    "response": provider_response,
                    "session_id": self.session_manager.session_id,
                },
            )

            return provider_response

        except WebSocketConnectionError as e:
            if connection:
                self.session_manager.mark_broken(connection)

            self.coordinator.emit(
                "provider:error",
                {"provider": self.name, "error_type": "WebSocketConnectionError", "error_message": str(e)},
            )
            raise

        except AudioFormatError as e:
            self.coordinator.emit(
                "provider:validation_error",
                {"provider": self.name, "error_type": "AudioFormatError", "error_message": str(e)},
            )
            raise

        except Exception as e:
            self.coordinator.emit(
                "provider:error",
                {"provider": self.name, "error_type": type(e).__name__, "error_message": str(e)},
            )
            raise

    def parse_tool_calls(self: "OpenAIRealtimeProvider", response: "ProviderResponse") -> list["ToolCall"]:
        """Parse tool calls from provider response.

        Per docs/API_CONTRACT.md: Tool calls already parsed during complete(),
        stored in response.tool_calls field.

        Args:
            response: ProviderResponse from complete()

        Returns:
            list[ToolCall]: Extracted tool calls (empty if none)
        """
        return response.tool_calls or []

    def _extract_instructions(self: "OpenAIRealtimeProvider", messages: list[dict[str, Any]]) -> str:
        """Extract system messages and combine into instructions.

        Per docs/API_CONTRACT.md: System messages → concatenated instructions string

        Args:
            messages: Message list

        Returns:
            str: Combined system instructions
        """
        system_messages = [msg for msg in messages if msg.get("role") == "system"]

        if not system_messages:
            return ""

        instructions = []
        for msg in system_messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                instructions.append(content)
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        instructions.append(block.get("text", ""))

        return "\n".join(instructions)

    def _extract_audio(self: "OpenAIRealtimeProvider", messages: list[dict[str, Any]]) -> bytes:
        """Extract audio data from last user message.

        Per docs/API_CONTRACT.md: Find last user message, extract audio content block

        Args:
            messages: Message list

        Returns:
            bytes: PCM16 audio data

        Raises:
            AudioFormatError: No audio found or invalid format
        """
        user_messages = [msg for msg in messages if msg.get("role") == "user"]

        if not user_messages:
            raise AudioFormatError("No user message found")

        last_user_msg = user_messages[-1]
        content = last_user_msg.get("content", [])

        if isinstance(content, str):
            raise AudioFormatError("User message has text content, expected audio")

        if not isinstance(content, list):
            raise AudioFormatError("User message content must be list")

        for block in content:
            if block.get("type") == "audio":
                audio_data = block.get("data")
                if not isinstance(audio_data, bytes):
                    raise AudioFormatError("Audio data must be bytes")
                return audio_data

        raise AudioFormatError("No audio content block found in user message")

    def _extract_usage(self: "OpenAIRealtimeProvider", ws_response: dict[str, Any]) -> dict[str, int]:
        """Extract token usage from WebSocket response.

        Args:
            ws_response: Full WebSocket response dict

        Returns:
            dict: Usage with input/output token counts
        """
        usage = ws_response.get("response", {}).get("usage", {})

        return {"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)}

    def _parse_tool_calls_from_ws_response(
        self: "OpenAIRealtimeProvider", ws_response: dict[str, Any]
    ) -> list["ToolCall"]:
        """Parse tool calls from WebSocket response.

        Per docs/FUNCTION_CALLING.md: Check for function_call_arguments.done events

        Args:
            ws_response: Full WebSocket response

        Returns:
            list[ToolCall]: Parsed tool calls (empty if none)
        """
        from amplifier_core.models import ToolCall

        msg_type = ws_response.get("type", "")

        if msg_type == "response.function_call_arguments.done":
            call_id = ws_response.get("call_id")
            name = ws_response.get("name")
            arguments_str = ws_response.get("arguments", "{}")

            try:
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse tool call arguments: {arguments_str}")
                arguments = {}

            return [ToolCall(tool=name, arguments=arguments, id=call_id)]

        return []
