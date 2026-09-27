"""The coding environment: tasks, isolated Git workspaces and applying agent output.

Each task directory holds:
  spec.md          the contract shown to coder and reviewer
  starter.py       the stub committed as the baseline `solution.py`
  test_visible.py  the deterministic acceptance tests (shown to coder and reviewer)
  test_hidden.py   held-out tests; ground truth only, never shown to any agent
  reference.py     a reference solution, used only by this repo's own tests

Workspace isolation follows agent-workflow-orchestrator (`gitops.py`): a private Git repository per
episode, a frozen baseline commit, and the candidate frozen as a commit whose diff is recorded.
Verification never runs in that workspace: `verifiers.pytest_verifier` copies the frozen
`solution.py` into a fresh directory (the orchestrator's "fresh-checkout evaluation").
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

VISIBLE, HIDDEN = "test_visible.py", "test_hidden.py"
_FENCE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class Task:
    task_id: str
    root: Path

    @property
    def spec(self) -> str:
        return (self.root / "spec.md").read_text()

    @property
    def starter(self) -> str:
        return (self.root / "starter.py").read_text()

    @property
    def visible_tests(self) -> str:
        return (self.root / VISIBLE).read_text()

    def file_hashes(self) -> dict[str, str]:
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.root.iterdir()) if p.is_file()}


def load_tasks(tasks_dir: Path, task_ids: list[str] | None = None) -> list[Task]:
    ids = task_ids or sorted(p.name for p in tasks_dir.iterdir() if (p / "spec.md").exists())
    return [Task(t, tasks_dir / t) for t in ids]


def extract_solution(text: str | None) -> str | None:
    """Return the single fenced Python block in a reply, or None (a protocol failure).

    The contract is exactly one fenced block; several blocks are ambiguous and rejected rather than
    guessed at.
    """
    if not text:
        return None
    blocks = _FENCE.findall(text)
    if len(blocks) != 1 or not blocks[0].strip():
        return None
    return blocks[0]


def _git(cwd: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "arl", "GIT_AUTHOR_EMAIL": "arl@localhost",
           "GIT_COMMITTER_NAME": "arl", "GIT_COMMITTER_EMAIL": "arl@localhost",
           "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(cwd), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd, env=env,
                          check=True, capture_output=True, text=True).stdout


class Workspace:
    """A private Git repo: baseline = starter + visible tests; each candidate is a commit."""

    def __init__(self, task: Task, path: Path):
        self.task, self.path = task, path
        path.mkdir(parents=True)
        (path / "solution.py").write_text(task.starter)
        (path / VISIBLE).write_text(task.visible_tests)
        _git(path, "init", "-q", "-b", "main")
        _git(path, "add", "-A")
        _git(path, "commit", "-q", "-m", "baseline")
        self.baseline_sha = _git(path, "rev-parse", "HEAD").strip()

    def commit_candidate(self, code: str, label: str) -> dict:
        """Freeze `code` as solution.py. Returns sha and diff against the baseline."""
        (self.path / "solution.py").write_text(code)
        _git(self.path, "add", "solution.py")
        _git(self.path, "commit", "-q", "--allow-empty", "-m", label)
        sha = _git(self.path, "rev-parse", "HEAD").strip()
        diff = _git(self.path, "diff", self.baseline_sha, sha)
        return {"sha": sha, "diff": diff, "code_sha256": hashlib.sha256(code.encode()).hexdigest()}
