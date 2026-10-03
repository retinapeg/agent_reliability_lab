from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "experiments" / "coding_cross_review" / "tasks"


@pytest.fixture
def tasks_dir() -> Path:
    return TASKS


@pytest.fixture(autouse=True)
def _no_real_pricing(tmp_path, monkeypatch):
    """Tests never read ~/.agent-arena/pricing.toml; a test that needs prices passes a table."""
    monkeypatch.setenv("AGENT_PRICING_FILE", str(tmp_path / "no-pricing.toml"))
