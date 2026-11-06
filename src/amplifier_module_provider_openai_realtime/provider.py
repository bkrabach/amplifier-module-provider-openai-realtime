"""OpenAI Realtime provider implementation."""

import asyncio
import json
import logging
from typing import TYPE_CHECKING
from typing import Any
from typing import Union

from .audio_codec import validate_audio_format
from .exceptions import AudioFormatError
from .exceptions import SessionInitializationError
from .exceptions import WebSocketConnectionError
from .session_mgmt import SessionManager

if TYPE_CHECKING:
    from amplifier_core.message_models import ChatRequest
    from amplifier_core.message_models import ChatResponse as ProviderResponse
    from amplifier_core.message_models import ToolCall

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
        self.raw = config.get("raw", False)
        if type(self.raw) is not bool:
            raise ValueError("raw must be a boolean")

    def get_info(self):
        from amplifier_core import ProviderInfo

        return ProviderInfo(
            id=self.name,
            display_name="OpenAI Realtime",
            credential_env_vars=["OPENAI_API_KEY"],
            capabilities=["audio", "tools"],
            defaults={"model": self.config.get("model")},
        )

    async def list_models(self):
        # No authoritative model catalog/context limits are implemented here.
        # Returning no catalog permits explicit model entry without invented limits.
        return []

    async def complete(
        self: "OpenAIRealtimeProvider", messages: Union[list[dict[str, Any]], "ChatRequest"], **kwargs: Any
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
            messages: Message list in Amplifier format or ChatRequest object
            **kwargs: Additional parameters (unused)

        Returns:
            ProviderResponse: Response with audio data in raw field

        Raises:
            AudioFormatError: Invalid audio format
            WebSocketConnectionError: Connection failed
        """
        from amplifier_core.utils import redact_secrets
        from amplifier_core.message_models import TextBlock, Usage
        from amplifier_core.message_models import ChatRequest
        from amplifier_core.message_models import ChatResponse as ProviderResponse

        # Handle ChatRequest format (from orchestrator)
        if isinstance(messages, ChatRequest):
            message_dicts = [
                {"role": msg.role if isinstance(msg.role, str) else msg.role.value, "content": msg.content}
                for msg in messages.messages
            ]
        else:
            message_dicts = messages

        for message in message_dicts:
            content = message.get("content")
            if isinstance(content, list):
                blocks = [
                    block.model_dump() if hasattr(block, "model_dump") else block
                    for block in content
                ]
                if blocks and all(block.get("type") == "text" for block in blocks):
                    message["content"] = "\n".join(
                        block.get("text", "") for block in blocks
                    )
                else:
                    message["content"] = blocks
        instructions = self._extract_instructions(message_dicts)
        connection = None

        try:
            if self.coordinator and hasattr(self.coordinator, "hooks"):
                await self.coordinator.hooks.emit(
                    "provider:request",
                    {
                        "provider": self.name,
                        "model": self.config.get("model", "gpt-4o-realtime-preview-2024-12-17"),
                        "messages": message_dicts,
                    },
                )

            if self.coordinator and hasattr(self.coordinator, "hooks"):
                event = {
                    "provider": self.name,
                    "model": self.config.get("model"),
                    "message_count": len(message_dicts),
                }
                if self.raw:
                    event["raw"] = redact_secrets(
                        {"messages": message_dicts, "instructions": instructions}
                    )
                await self.coordinator.hooks.emit("llm:request", event)

            connection = await self.session_manager.get_or_create_connection()

            await self.session_manager.ensure_session_initialized(instructions)

            # Extract content from last user message (text or audio)
            last_user_msg = next((msg for msg in reversed(message_dicts) if msg.get("role") == "user"), None)

            if not last_user_msg:
                raise ValueError("No user message found in messages")

            content = last_user_msg.get("content", "")

            # Handle text input (send as text, OpenAI responds with audio)
            if isinstance(content, str):
                await connection.send(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": content}],
                        },
                    }
                )
                await connection.send({"type": "response.create"})
                response = await connection.receive_audio()
            else:
                # Handle audio input
                audio_data = self._extract_audio(message_dicts)
                validate_audio_format(audio_data)
                await connection.send_audio(audio_data)
                response = await connection.receive_audio()

            tool_calls = self._parse_tool_calls_from_ws_response(response["full_response"])

            class RealtimeResponse(ProviderResponse):
                # Preserve the direct caller audio accessor while satisfying the
                # current typed provider contract. Audio is not plain-text context.
                raw: dict[str, Any]

            usage = self._extract_usage(response["full_response"])
            provider_response = RealtimeResponse(
                content=[TextBlock(text=response["transcript"])],
                raw={
                    "audio_data": response["audio_data"],
                    "audio_format": "pcm16",
                    "sample_rate": 24000,
                    "transcript": response["transcript"],
                    "session_id": self.session_manager.session_id or "",
                    "websocket_response": response["full_response"],
                },
                usage=Usage(
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    total_tokens=usage["input_tokens"] + usage["output_tokens"],
                ),
                tool_calls=tool_calls if tool_calls else None,
                finish_reason="tool_calls" if tool_calls else "stop",
            )

            if self.coordinator and hasattr(self.coordinator, "hooks"):
                await self.coordinator.hooks.emit(
                    "provider:response",
                    {
                        "provider": self.name,
                        "model": self.config.get("model", "gpt-4o-realtime-preview-2024-12-17"),
                        "response": provider_response,
                        "session_id": self.session_manager.session_id,
                    },
                )

            if self.coordinator and hasattr(self.coordinator, "hooks"):
                await self.coordinator.hooks.emit(
                    "llm:response",
                    {
                        "provider": self.name,
                        "model": self.config.get("model"),
                        "status": "ok",
                        "usage": provider_response.usage.model_dump(),
                    },
                )

            return provider_response

        except asyncio.CancelledError:
            # An interrupted receive leaves unread events. Never reuse that
            # connection and attribute its remaining audio to the next turn.
            await self.session_manager.cleanup()
            raise

        except (WebSocketConnectionError, SessionInitializationError) as e:
            if connection:
                self.session_manager.mark_broken(connection)
                await connection.close()

            if self.coordinator and hasattr(self.coordinator, "hooks"):
                await self.coordinator.hooks.emit(
                    "provider:error",
                    {"provider": self.name, "error_type": type(e).__name__, "error_message": str(e)},
                )
            raise

        except AudioFormatError as e:
            if self.coordinator and hasattr(self.coordinator, "hooks"):
                await self.coordinator.hooks.emit(
                    "provider:validation_error",
                    {"provider": self.name, "error_type": "AudioFormatError", "error_message": str(e)},
                )
            raise

        except Exception as e:
            if self.coordinator and hasattr(self.coordinator, "hooks"):
                await self.coordinator.hooks.emit(
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

        return {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }

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
        from amplifier_core.message_models import ToolCall

        # The receiver returns the terminal response.done envelope. Support the
        # standalone arguments event for existing direct callers as well.
        if ws_response.get("type") == "response.function_call_arguments.done":
            items = [ws_response]
        else:
            items = [
                item
                for item in ws_response.get("response", {}).get("output", [])
                if item.get("type") == "function_call"
            ]
        calls = []
        for item in items:
            try:
                arguments = json.loads(item.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError) as exc:
                # Never execute a malformed model call with fabricated empty args
                # or echo its possibly sensitive argument payload to logs.
                raise ValueError(
                    "Realtime function arguments are not valid JSON"
                ) from exc
            if not isinstance(arguments, dict):
                raise ValueError("Realtime function arguments must be an object")
            calls.append(
                ToolCall(
                    name=item.get("name"), arguments=arguments, id=item.get("call_id")
                )
            )
        return calls
