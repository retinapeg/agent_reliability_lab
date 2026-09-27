from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "experiments" / "coding_cross_review" / "tasks"


@pytest.fixture
def tasks_dir() -> Path:
    return TASKS
