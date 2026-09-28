from pathlib import Path

from asnwero_bot.storage import Storage
from asnwero_bot.text import normalize_text


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


def test_normalize_text_preserves_dialogue_lines():
    assert normalize_text("Аня: привет\n\nБорис: привет!   Как дела?", 200) == (
        "Аня: привет\nБорис: привет! Как дела?"
    )
