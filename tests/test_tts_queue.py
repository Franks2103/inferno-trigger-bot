import asyncio
from types import SimpleNamespace

import pytest

from services.tts_bridge_queue import TtsBridgeQueue, TtsItem


@pytest.mark.asyncio
async def test_queue_enforces_user_and_guild_limits(monkeypatch):
    queue = TtsBridgeQueue(
        SimpleNamespace(),
        SimpleNamespace(id=1),
        SimpleNamespace(),
        SimpleNamespace(),
    )
    blocker = asyncio.Event()

    async def wait_forever():
        await blocker.wait()

    monkeypatch.setattr(queue, "_worker", wait_forever)
    for index in range(3):
        assert queue.enqueue(TtsItem(10, "Ana", "hola", index)) is None
    assert queue.enqueue(TtsItem(10, "Ana", "hola", 4)) == "user_queue_full"

    for index in range(11, 28):
        assert queue.enqueue(TtsItem(index, "Otro", "hola", index)) is None
    assert queue.enqueue(TtsItem(99, "Extra", "hola", 99)) == "guild_queue_full"

    queue._task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await queue._task
