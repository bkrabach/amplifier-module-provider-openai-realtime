"""Bounded initialization transcripts through complete -> manager -> real adapter.

Only websockets.connect is replaced by a serialized in-memory wire. This does
not assert live beta availability or qualify GA headers/session shapes/models.
"""
import asyncio
import copy
import json

import pytest
from websockets.exceptions import ConnectionClosedOK
from websockets.frames import Close

from amplifier_module_provider_openai_realtime.exceptions import (
    SessionInitializationError, WebSocketConnectionError,
)
from test_websocket_transcript import MODEL, PCM, Wire, request, setup_provider, turn

CREATED = {"type": "session.created", "session": {"id": "session-1"}}
UPDATED = {"type": "session.updated", "session": {"id": "session-1"}}
CONVERSATION = {"type": "conversation.created", "event_id": "conversation-event-1",
                "conversation": {"id": "conversation-1", "object": "realtime.conversation"}}


class InitializationWire(Wire):
    def __init__(self, handshake, *, prefix="response.output_audio", close_after=False, raw_after=False):
        super().__init__([turn(prefix)], initial_created=False)
        self.handshake = copy.deepcopy(handshake)
        self.close_after = close_after
        self.raw_after = raw_after

    async def send(self, payload):
        message = json.loads(payload)
        if message["type"] == "session.update":
            self.sent.append(message)
            self.events.extend(copy.deepcopy(self.handshake))
        else:
            await super().send(payload)

    async def recv(self):
        if not self.events and self.close_after:
            raise ConnectionClosedOK(Close(1000, "PRIVATE"), Close(1000, "PRIVATE"), True)
        if not self.events and self.raw_after:
            return "PRIVATE invalid JSON"
        return await super().recv()


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["response.audio", "response.output_audio"])
@pytest.mark.parametrize("resource", [CONVERSATION["conversation"], {}, {"id": None, "object": None}])
async def test_documented_conversation_creation_does_not_confirm_configuration(monkeypatch, prefix, resource):
    handshake = [CREATED, {**CONVERSATION, "conversation": resource}, UPDATED]
    wire = InitializationWire(handshake, prefix=prefix)
    p, connect, _ = setup_provider(monkeypatch, wire)
    try:
        result = await asyncio.wait_for(p.complete(request("typed")), 2)
        assert result.raw["audio_data"] == PCM and result.raw["transcript"] == "Hello"
        assert result.raw["session_id"] == "session-1"
        assert wire.received[:3] == handshake
        assert wire.received[-1]["type"] == "response.done"
        assert [m["type"] for m in wire.sent] == ["session.update", "conversation.item.create", "response.create"]
        assert wire.sent[0]["session"] == {"instructions": "Be brief", "voice": "alloy", "temperature": .7}
        assert p.session_manager._instructions_set and p.session_manager.session_id == "session-1"
        connect.assert_awaited_once_with("wss://api.openai.com/v1/realtime?model="+MODEL,
            additional_headers={"Authorization": "Bearer fixture-only", "OpenAI-Beta": "realtime=v1"})
    finally:
        await p.session_manager.cleanup()
    assert wire.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("handshake,exception", [
    ([CREATED, CONVERSATION, {"type": "error", "error": {"message": "PRIVATE"}}], SessionInitializationError),
    ([CREATED, CONVERSATION, {"type": "session.updated", "session": {"id": "other"}}], SessionInitializationError),
    ([CREATED, CONVERSATION, {"type": "session.updated", "session": {}}], SessionInitializationError),
    ([CREATED, CONVERSATION, {"type": "future.initialization"}], SessionInitializationError),
    ([CREATED, CONVERSATION, []], WebSocketConnectionError),
    ([CREATED, {"type": "conversation.created", "event_id": "e"}, UPDATED], SessionInitializationError),
    ([CREATED, {**CONVERSATION, "conversation": {"object": "unrelated"}}, UPDATED], SessionInitializationError),
    ([CREATED, {**CONVERSATION, "conversation": {"id": 2}}, UPDATED], SessionInitializationError),
    ([CREATED, {**CONVERSATION, "event_id": ""}, UPDATED], SessionInitializationError),
    ([CONVERSATION, UPDATED], SessionInitializationError),
    ([CREATED, CONVERSATION, CONVERSATION, UPDATED], SessionInitializationError),
    ([CREATED, CREATED, CREATED, UPDATED], SessionInitializationError),
])
async def test_invalid_initialization_never_sends_input_or_accepts_session(monkeypatch, handshake, exception):
    wire = InitializationWire(handshake)
    p, _, hooks = setup_provider(monkeypatch, wire)
    with pytest.raises(exception) as caught:
        await asyncio.wait_for(p.complete(request()), 2)
    assert "PRIVATE" not in str(caught.value)
    assert [m["type"] for m in wire.sent] == ["session.update"]
    assert len(wire.received) <= 3
    assert wire.closed == 1 and p.session_manager.connection is None
    assert p.session_manager.session_id is None and not p.session_manager._instructions_set
    assert not any(c.args[0] == "llm:response" for c in hooks.emit.call_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("close_after,raw_after", [(True, False), (False, True)])
async def test_close_or_malformed_json_while_waiting_for_update_cleans_up(monkeypatch, close_after, raw_after):
    wire = InitializationWire([CREATED, CONVERSATION], close_after=close_after, raw_after=raw_after)
    p, _, _ = setup_provider(monkeypatch, wire)
    with pytest.raises(WebSocketConnectionError) as caught:
        await asyncio.wait_for(p.complete(request()), 2)
    assert "PRIVATE" not in str(caught.value)
    assert wire.closed == 1 and p.session_manager.connection is None
    assert [m["type"] for m in wire.sent] == ["session.update"]


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["cancel", "caller-timeout"])
async def test_benign_event_without_update_waits_and_interruption_reconnects(monkeypatch, interruption):
    wire = InitializationWire([CREATED, CONVERSATION])
    replacement = InitializationWire([CREATED, CONVERSATION, UPDATED])
    p, connect, _ = setup_provider(monkeypatch, wire, more_wires=[replacement])
    # Synchronize with recv waiting, rather than guessing an arbitrary sleep.
    task = asyncio.create_task(p.complete(request()))
    try:
        await asyncio.wait_for(wire.blocked.wait(), 2)
        assert not task.done() and not p.session_manager._instructions_set
        assert p.session_manager.session_id is None
        assert [m["type"] for m in wire.sent] == ["session.update"]
        if interruption == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(task, .02)
        assert wire.closed == 1 and p.session_manager.connection is None
        result = await asyncio.wait_for(p.complete(request()), 2)
        assert result.raw["audio_data"] == PCM and connect.await_count == 2
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await p.session_manager.cleanup()
    assert replacement.closed == 1
