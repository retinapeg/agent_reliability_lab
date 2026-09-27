"""Run directories and append-only trace files.

Layout of one run (never overwritten; the run ID is a UTC timestamp plus a config hash):

  results/runs/<run_id>/
    run.json          config, config SHA-256, task file hashes, git SHA, tool versions, start time
    attempts.jsonl    one line written BEFORE each episode's first model call
    episodes.jsonl    one complete episode record per line (the analysis input)
    raw/              full CLI event streams per call (gitignored: session IDs, local paths)

The attempts-before-calls rule and raw/summary split come from agentic-physics-bench `run_v2.py`:
an interrupted episode still leaves a record, so nothing is silently re-run or dropped.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

SCHEMA_VERSION = "arl-episode-v1"

EPISODE_REQUIRED = {"schema", "run_id", "episode_id", "task_id", "status", "calls", "coder",
                    "visible", "hidden", "review", "revision"}

_PATH = re.compile(r"(?:/private)?/(?:Users|home|var/folders|tmp)/[^\s\"'`<>]*")


def redact(text: str | None) -> str | None:
    """Remove absolute local paths before text enters a committed file."""
    return None if text is None else _PATH.sub("<path>", text.replace(str(Path.home()), "~"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def new_run_id(config_text: str, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ") + "-" + sha256_text(config_text)[:8]


class RunStore:
    def __init__(self, results_dir: Path, run_id: str):
        self.run_id = run_id
        self.dir = results_dir / "runs" / run_id
        if self.dir.exists():
            raise FileExistsError(f"run directory already exists, refusing to overwrite: {self.dir}")
        (self.dir / "raw").mkdir(parents=True)

    def write_run_meta(self, meta: dict) -> None:
        (self.dir / "run.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    def append(self, name: str, record: dict) -> None:
        with (self.dir / name).open("a") as f:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")

    def write_raw(self, episode_id: str, index: int, role: str, raw: dict) -> str:
        path = self.dir / "raw" / f"{episode_id}-{index:02d}-{role}.json"
        path.write_text(json.dumps(raw, indent=1))
        return str(path.relative_to(self.dir))


def load_episodes(run_dir: Path) -> list[dict]:
    path = run_dir / "episodes.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for r in rows:
        validate_episode(r)
    return rows


def validate_episode(r: dict) -> None:
    missing = EPISODE_REQUIRED - r.keys()
    if missing:
        raise ValueError(f"episode {r.get('episode_id')} missing fields: {sorted(missing)}")
    if r["schema"] != SCHEMA_VERSION:
        raise ValueError(f"episode {r['episode_id']} has schema {r['schema']!r}")
    if r["status"] not in ("complete", "system_failure", "protocol_failure"):
        raise ValueError(f"episode {r['episode_id']} has unknown status {r['status']!r}")
