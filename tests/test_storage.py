from pathlib import Path

from asnwero_bot.storage import Storage


async def test_storage_saves_and_clears_task(tmp_path: Path):
    storage = Storage(tmp_path / "test.sqlite3")
    await storage.init()

    await storage.save_task(42, "source", stage="tone")
    task = await storage.get_task(42)

    assert task is not None
    assert task.source_text == "source"
    assert task.stage == "tone"

    await storage.clear_task(42)

    assert await storage.get_task(42) is None


async def test_storage_counts_recent_generations(tmp_path: Path):
    storage = Storage(tmp_path / "test.sqlite3")
    await storage.init()

    await storage.record_generation(42)
    await storage.record_generation(42)

    assert await storage.count_recent_generations(42) == 2
    assert await storage.count_recent_generations(7) == 0

