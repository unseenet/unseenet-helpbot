"""While the key ripens, the updater is told not to restart the bot (unseenet#827)."""

import asyncio

from unseenet_helpbot import runner


def test_the_busy_file_is_there_while_ripening_and_gone_after(tmp_path):
    path = tmp_path / "state" / "busy"

    async def go():
        async with runner.busy(path):
            await asyncio.sleep(0.05)
            assert path.exists()
        assert not path.exists()
    asyncio.run(go())
