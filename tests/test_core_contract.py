"""Offline transport proves Core compatibility without opening a voice call."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from amplifier_core import ChatRequest, ChatResponse, Message, TextBlock

from amplifier_module_provider_openai_realtime.provider import OpenAIRealtimeProvider


@pytest.mark.asyncio
async def test_typed_text_request_preserves_audio_and_usage():
    p = OpenAIRealtimeProvider("fake-key", {}, None)
    conn = SimpleNamespace(
        send=AsyncMock(),
        receive_audio=AsyncMock(
            return_value={
                "audio_data": b"audio",
                "transcript": "Hello",
                "full_response": {
                    "type": "response.done",
                    "response": {
                        "output": [],
                        "usage": {"input_tokens": 15, "output_tokens": 20},
                    },
                },
            }
        ),
    )
    p.session_manager.get_or_create_connection = AsyncMock(return_value=conn)
    p.session_manager.ensure_session_initialized = AsyncMock()
    result = await p.complete(
        ChatRequest(
            messages=[
                Message(role="system", content="Instructions"),
                Message(role="user", content=[TextBlock(text="Hello")]),
            ]
        )
    )
    assert isinstance(result, ChatResponse)
    assert result.content[0].text == "Hello" and result.raw["audio_data"] == b"audio"
    assert result.usage.input_tokens == 15 and result.usage.total_tokens == 35
    assert conn.send.call_args_list[0].args[0]["item"]["content"][0]["text"] == "Hello"
    p.session_manager.ensure_session_initialized.assert_awaited_once_with(
        "Instructions"
    )
    assert p.parse_tool_calls(result) == []
    assert p.get_info().id == "openai-realtime" and await p.list_models() == []


def test_function_call_uses_current_tool_contract():
    p = OpenAIRealtimeProvider("fake-key", {}, None)
    calls = p._parse_tool_calls_from_ws_response(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "call-1",
            "name": "lookup",
            "arguments": '{"query":"hello"}',
        }
    )
    assert calls[0].name == "lookup" and calls[0].arguments == {"query": "hello"}


def test_terminal_envelope_preserves_calls_and_rejects_broken_arguments():
    p = OpenAIRealtimeProvider("fake-key", {}, None)
    item = {
        "type": "function_call",
        "call_id": "call-1",
        "name": "lookup",
        "arguments": '{"query":"hello"}',
    }
    calls = p._parse_tool_calls_from_ws_response(
        {"type": "response.done", "response": {"output": [item]}}
    )
    assert calls[0].id == "call-1" and calls[0].arguments == {"query": "hello"}
    for bad in ("{", "[]"):
        with pytest.raises(ValueError, match="Realtime function arguments"):
            p._parse_tool_calls_from_ws_response(
                {
                    "type": "response.done",
                    "response": {"output": [dict(item, arguments=bad)]},
                }
            )
