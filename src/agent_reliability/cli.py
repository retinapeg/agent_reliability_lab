"""Command line: `run` an experiment from a frozen config, `analyze` a run without model calls."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

from .agents.cli_agent import make_agent
from .analysis.summarize import analyze
from .environments.coding.environment import load_tasks
from .review.reviewer import FlagRule
from .runners.cross_review import BatchStopped, Episode, EpisodeConfig, environment_facts
from .traces.store import RunStore, new_run_id, sha256_text

ROOT = Path.cwd()


def cmd_run(args: argparse.Namespace) -> int:
    config_text = Path(args.config).read_text()
    cfg = json.loads(config_text)
    tasks = load_tasks(ROOT / cfg["tasks_dir"], args.tasks or cfg.get("task_ids"))
    run_id = new_run_id(config_text)
    if args.label:
        run_id += f"-{args.label}"
    store = RunStore(ROOT / "results", run_id)
    meta = {"run_id": run_id, "config_path": args.config, "config": cfg,
            "config_sha256": sha256_text(config_text),
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "tasks": {t.task_id: t.file_hashes() for t in tasks},
            "environment": environment_facts(), "stopped": None}
    store.write_run_meta(meta)
    coder, reviewer = make_agent(cfg["coder"]), make_agent(cfg["reviewer"])
    ecfg = EpisodeConfig(max_retries=cfg.get("max_retries", 1), revision=cfg.get("revision", True),
                         flag_rule=FlagRule(tuple(cfg["flag_rule"]["severities"]),
                                            cfg["flag_rule"]["min_confidence"]))
    try:
        for rep in range(cfg.get("repetitions", 1)):
            for task in tasks:
                rec = Episode(task, coder, reviewer, store, ecfg, rep=rep).run()
                rv = rec["review"] or {}
                print(f"[{rec['episode_id']}] status={rec['status']} "
                      f"visible={(rec['visible'] or {}).get('passed')} "
                      f"hidden={(rec['hidden'] or {}).get('passed')} flagged={rv.get('flagged')}",
                      flush=True)
    except BatchStopped as exc:
        meta["stopped"] = f"control violation: {exc}"
        print(f"BATCH STOPPED: {exc}", file=sys.stderr)
    meta["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    store.write_run_meta(meta)
    print(f"run directory: {store.dir}")
    return cmd_analyze(argparse.Namespace(run_dir=str(store.dir), no_latest=args.no_latest))


def cmd_analyze(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir) if args.run_dir else _latest_run()
    metrics, summary = analyze(run_dir)
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    (run_dir / "summary.md").write_text(summary)
    if not args.no_latest:
        shutil.copyfile(run_dir / "summary.md", ROOT / "results" / "latest_summary.md")
        shutil.copyfile(run_dir / "metrics.json", ROOT / "results" / "latest_metrics.json")
    print(summary)
    return 0


def _latest_run() -> Path:
    pointer = ROOT / "results" / "LATEST"
    if pointer.exists():
        return ROOT / "results" / "runs" / pointer.read_text().strip()
    runs = sorted((ROOT / "results" / "runs").iterdir())
    return runs[-1]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="arl")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the experiment (calls models)")
    r.add_argument("--config", required=True)
    r.add_argument("--tasks", nargs="*", help="subset of task IDs (smoke tests)")
    r.add_argument("--label", help="suffix for the run ID, e.g. smoke")
    r.add_argument("--no-latest", action="store_true", help="do not update results/latest_*")
    a = sub.add_parser("analyze", help="recompute metrics and summary from a run directory")
    a.add_argument("run_dir", nargs="?", help="defaults to results/LATEST")
    a.add_argument("--no-latest", action="store_true")
    args = p.parse_args(argv)
    return cmd_run(args) if args.cmd == "run" else cmd_analyze(args)
