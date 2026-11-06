"""Offline serialized WebSocket transcripts through the actual provider boundary.

No provider/session/receiver method is replaced. Only websockets.connect returns
an in-memory wire. The current event names follow OpenAI's official Realtime
server-events reference; legacy names remain accepted. This is not GA session
creation/model entitlement or microphone qualification.
"""
import asyncio
import base64
from collections import deque
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from amplifier_core import ChatRequest, ChatResponse, Message
from amplifier_module_provider_openai_realtime.provider import OpenAIRealtimeProvider
from amplifier_module_provider_openai_realtime.exceptions import (
    AudioFormatError, SessionInitializationError, WebSocketConnectionError,
)

PCM = b"\x00\x01\x02\x03\x04\x05\x06\x07"
MODEL = "explicit-voice-route"


def turn(prefix, identity="r1", *, pcm=PCM, transcript="Hello", status="completed"):
    def event(kind, suffix, **fields):
        return {"type": kind, "event_id": identity+suffix, "response_id": identity,
                "output_index": 0, "content_index": 0, "item_id": identity+"-item", **fields}
    return [
        {"type": "response.created", "event_id": identity+"-created", "response": {"id": identity, "status": "in_progress"}},
        {"type": "response.output_item.added", "response_id": identity, "item": {"id": identity+"-item"}},
        # Both chunks have their own padding. Joining base64 strings loses chunk 2.
        event(prefix+".delta", "-a1", delta=base64.b64encode(pcm[:2]).decode()),
        event(prefix+".delta", "-a2", delta=base64.b64encode(pcm[2:]).decode()),
        event(prefix+".done", "-audio-done"),
        event(prefix+"_transcript.delta", "-t1", delta="Hel"),
        event(prefix+"_transcript.delta", "-t2", delta="lo"),
        event(prefix+"_transcript.done", "-transcript-done", transcript=transcript),
        {"type": "response.done", "event_id": identity+"-done", "response": {
            "id": identity, "status": status, "output": [],
            "usage": {"input_tokens": 3, "output_tokens": 5},
        }},
    ]


class Wire:
    """Strict serialized transport that confirms configuration before generation."""
    def __init__(self, turns, *, setup=None, initial_created=True):
        self.turns = deque(copy.deepcopy(turns))
        self.events = deque([{"type": "session.created", "session": {"id": "session-1"}}] if initial_created else [])
        self.setup = setup if setup is not None else {"type": "session.updated", "session": {"id": "session-1"}}
        self.sent = []
        self.received = []
        self.closed = 0
        self.updated = False
        self.blocked = asyncio.Event()
        self.waiter = asyncio.Event()

    async def send(self, payload):
        message = json.loads(payload)
        self.sent.append(message)
        if message["type"] == "session.update":
            self.events.append(copy.deepcopy(self.setup))
        if message["type"] == "response.create":
            assert self.updated, "must consume session.updated before response.create"
            self.events.extend(self.turns.popleft())

    async def recv(self):
        if not self.events:
            self.blocked.set()
            await self.waiter.wait()
            raise AssertionError("Unexpected end of synthetic transcript")
        message = self.events.popleft()
        self.received.append(message)
        if isinstance(message, dict) and message.get("type") == "session.updated":
            self.updated = True
        return json.dumps(message)

    async def close(self):
        self.closed += 1


def setup_provider(monkeypatch, wire, *, more_wires=()):
    connect = AsyncMock(side_effect=[wire, *more_wires])
    monkeypatch.setattr("amplifier_module_provider_openai_realtime.websocket.websockets.connect", connect)
    hooks = SimpleNamespace(emit=AsyncMock())
    provider = OpenAIRealtimeProvider("fixture-only", {"model": MODEL, "voice": "alloy", "temperature": .7}, SimpleNamespace(hooks=hooks))
    return provider, connect, hooks


def request(kind="text"):
    if kind == "typed":
        return ChatRequest(model="ignored-per-call-model", messages=[Message(role="system", content="Be brief"), Message(role="user", content="Hello")])
    content = "Hello" if kind == "text" else [{"type": "audio", "data": PCM, "format": "pcm16", "sample_rate": 24000}]
    return [{"role": "system", "content": "Be brief"}, {"role": "user", "content": content}]


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["response.audio", "response.output_audio"])
@pytest.mark.parametrize("kind", ["text", "typed", "audio"])
async def test_complete_serialized_turn_preserves_voice_contract(monkeypatch, prefix, kind):
    wire = Wire([turn(prefix)])
    p, connect, hooks = setup_provider(monkeypatch, wire)
    try:
        result = await asyncio.wait_for(p.complete(request(kind)), 2)
        assert isinstance(result, ChatResponse)
        assert result.raw["audio_data"] == PCM
        assert result.raw["audio_format"] == "pcm16" and result.raw["sample_rate"] == 24000
        assert result.raw["session_id"] == "session-1"
        assert result.content[0].text == result.raw["transcript"] == "Hello"
        assert result.usage.total_tokens == 8 and result.finish_reason == "stop"
        assert result.raw["websocket_response"]["response"]["id"] == "r1"
        assert not wire.events and wire.received[-1]["type"] == "response.done"
        connect.assert_awaited_once_with("wss://api.openai.com/v1/realtime?model="+MODEL,
            additional_headers={"Authorization": "Bearer fixture-only", "OpenAI-Beta": "realtime=v1"})
        assert wire.sent[0] == {"type": "session.update", "session": {"instructions": "Be brief", "voice": "alloy", "temperature": .7}}
        expected_input = {"type": "input_audio", "audio": base64.b64encode(PCM).decode()} if kind == "audio" else {"type": "input_text", "text": "Hello"}
        assert wire.sent[1] == {"type": "conversation.item.create", "item": {"type": "message", "role": "user", "content": [expected_input]}}
        assert wire.sent[2] == {"type": "response.create"}
        assert await p.list_models() == [] and p.get_info().defaults["model"] == MODEL
        assert any(call.args[0] == "llm:response" for call in hooks.emit.call_args_list)
    finally:
        await p.session_manager.cleanup()
    assert wire.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["response.audio", "response.output_audio"])
async def test_duplicates_wrong_response_unknown_events_and_adjacent_turn(monkeypatch, prefix):
    first = turn(prefix)
    first[3:3] = [copy.deepcopy(first[2]),  # same event_id exactly once
                  {"type": "response.future_audio", "delta": "must-not-be-audio"},
                  {"type": prefix+".delta", "response_id": "other", "delta": "%%"},
                  {"type": "response.done", "response": {"id": "other", "status": "failed"}}]
    second = [copy.deepcopy(first[-1]), *turn(prefix, "r2", pcm=b"\x08\x09", transcript="Next")]
    wire = Wire([first, second])
    p, connect, _ = setup_provider(monkeypatch, wire)
    try:
        one = await asyncio.wait_for(p.complete(request()), 2)
        two = await asyncio.wait_for(p.complete(request()), 2)
        assert one.raw["audio_data"] == PCM and two.raw["audio_data"] == b"\x08\x09"
        assert two.raw["transcript"] == "Next" and two.raw["websocket_response"]["response"]["id"] == "r2"
        assert connect.await_count == 1
        assert [m["type"] for m in wire.sent].count("session.update") == 1
        assert [m["type"] for m in wire.sent].count("response.create") == 2
    finally:
        await p.session_manager.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["response.audio", "response.output_audio"])
@pytest.mark.parametrize("fault", ["server-error", "conflicting-duplicate", "invalid-base64", "after-done", "failed", "cancelled", "incomplete", "invalid-envelope", "invalid-index", "odd-pcm"])
async def test_invalid_turn_never_reports_success_and_closes_connection(monkeypatch, prefix, fault):
    events = turn(prefix)
    if fault == "server-error":
        events.insert(3, {"type": "error", "error": {"message": "PRIVATE"}})
    elif fault == "conflicting-duplicate":
        events.insert(3, {**events[2], "delta": base64.b64encode(b"other").decode()})
    elif fault == "invalid-base64":
        events[2]["delta"] = "PRIVATE%%"
    elif fault == "after-done":
        events.insert(5, {**events[2], "event_id": "late"})
    elif fault in ("failed", "cancelled", "incomplete"):
        events[-1]["response"]["status"] = fault
    elif fault == "invalid-envelope":
        events.insert(3, [])
    elif fault == "invalid-index":
        events[2]["content_index"] = -1
    elif fault == "odd-pcm":
        events = turn(prefix, pcm=b"odd")
    wire = Wire([events])
    p, _, hooks = setup_provider(monkeypatch, wire)
    with pytest.raises(WebSocketConnectionError) as exc:
        await asyncio.wait_for(p.complete(request()), 2)
    assert "PRIVATE" not in str(exc.value)
    assert p.session_manager.connection is None and wire.closed == 1
    assert not any(call.args[0] == "llm:response" for call in hooks.emit.call_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("setup", [{"type": "error", "error": {"message": "PRIVATE"}}, {"type": "session.updated", "session": {"id": "other"}}, {"type": "session.updated", "session": {}}, {"type": "response.done", "response": {"id": "bad"}}])
async def test_session_update_is_confirmed_not_just_created(monkeypatch, setup):
    wire = Wire([], setup=setup)
    p, _, _ = setup_provider(monkeypatch, wire)
    with pytest.raises(SessionInitializationError) as exc:
        await asyncio.wait_for(p.complete(request()), 2)
    assert "PRIVATE" not in str(exc.value)
    assert [m["type"] for m in wire.sent] == ["session.update"]
    assert p.session_manager.connection is None and wire.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("during_setup", [False, True])
async def test_cancellation_propagates_closes_and_next_call_reconnects(monkeypatch, during_setup):
    wire = Wire([turn("response.output_audio")[:3]])
    if during_setup:
        wire.setup = {"type": "session.created", "session": {"id": "session-1"}}
    replacement = Wire([turn("response.audio", "fresh")])
    p, connect, _ = setup_provider(monkeypatch, wire, more_wires=[replacement])
    task = asyncio.create_task(p.complete(request()))
    await asyncio.wait_for(wire.blocked.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert wire.closed == 1 and p.session_manager.connection is None
    result = await asyncio.wait_for(p.complete(request()), 2)
    assert result.raw["audio_data"] == PCM and result.raw["websocket_response"]["response"]["id"] == "fresh"
    assert connect.await_count == 2
    await p.session_manager.cleanup()


@pytest.mark.asyncio
async def test_legacy_full_audio_fallback_and_nonterminal_audio_done(monkeypatch):
    events = turn("response.audio")
    events[2:4] = []
    events[2]["audio"] = base64.b64encode(PCM).decode()
    wire = Wire([events])
    p, _, _ = setup_provider(monkeypatch, wire)
    result = await asyncio.wait_for(p.complete(request()), 2)
    assert result.raw["audio_data"] == PCM and result.raw["transcript"] == "Hello"
    assert wire.received[-1]["type"] == "response.done"
    await p.session_manager.cleanup()


@pytest.mark.asyncio
async def test_existing_input_validation_sends_no_audio_or_response(monkeypatch):
    wire = Wire([])
    p, _, _ = setup_provider(monkeypatch, wire)
    bad = request("audio")
    bad[-1]["content"][0]["data"] = b"odd"
    with pytest.raises(AudioFormatError):
        await asyncio.wait_for(p.complete(bad), 2)
    assert [m["type"] for m in wire.sent] == ["session.update"]
    await p.session_manager.cleanup()


@pytest.mark.asyncio
async def test_terminal_function_call_retains_typed_tool_contract(monkeypatch):
    events = turn("response.output_audio")
    events[-1]["response"]["output"] = [{"type": "function_call", "call_id": "call-1", "name": "lookup", "arguments": '{"q":"fixture"}'}]
    wire = Wire([events])
    p, _, _ = setup_provider(monkeypatch, wire)
    result = await asyncio.wait_for(p.complete(request()), 2)
    assert result.finish_reason == "tool_calls"
    assert p.parse_tool_calls(result)[0].arguments == {"q": "fixture"}
    await p.session_manager.cleanup()
