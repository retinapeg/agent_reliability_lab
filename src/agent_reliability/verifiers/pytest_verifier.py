"""Deterministic verification: run one pytest file against one frozen solution in a fresh directory.

Mirrors agent-workflow-orchestrator `evaluator.py`: checks run on a fresh copy of the frozen
candidate, never in the agent's workspace, with a timeout and a sanitized environment. Results are
parsed from JUnit XML rather than scraped from terminal output.

Not a security sandbox: candidate code runs as the current user. Acceptable here because tasks are
pure functions and every candidate is recorded, but see docs/architecture.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path


def run_tests(solution_code: str, test_file: Path, timeout_s: float = 60) -> dict:
    with tempfile.TemporaryDirectory(prefix="arl-verify-") as d:
        work = Path(d)
        (work / "solution.py").write_text(solution_code)
        (work / test_file.name).write_text(test_file.read_text())
        report = work / "report.xml"
        argv = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                f"--junitxml={report}", test_file.name]
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHONHASHSEED": "0", "HOME": os.environ.get("HOME", d)}
        started = time.monotonic()
        try:
            proc = subprocess.run(argv, cwd=work, env=env, capture_output=True, text=True,
                                  timeout=timeout_s)
            rc, out, timed_out = proc.returncode, proc.stdout + proc.stderr, False
        except subprocess.TimeoutExpired:
            rc, out, timed_out = None, "", True
        elapsed = round(time.monotonic() - started, 3)
        result = parse_junit(report.read_text()) if report.exists() else {
            "tests": 0, "failures": 0, "errors": 0, "failed_tests": []}
    result.update(returncode=rc, timed_out=timed_out, elapsed_s=elapsed,
                  output_tail=out[-1500:] if out else "")
    result["passed"] = (rc == 0 and not timed_out and result["tests"] > 0
                        and result["failures"] == 0 and result["errors"] == 0)
    return result


def parse_junit(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    tests = sum(int(s.get("tests", 0)) for s in suites)
    fails = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    failed = [c.get("name") for c in root.iter("testcase")
              if c.find("failure") is not None or c.find("error") is not None]
    return {"tests": tests, "failures": fails, "errors": errors, "failed_tests": failed}
