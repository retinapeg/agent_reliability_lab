"""Plot the frozen main run: python scripts/make_result_figure.py.

Requires matplotlib. run.json supplies the run identity and task list; the
adjacent episodes.jsonl supplies outcomes (run.json contains no test results).
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results/runs/20260927T192610Z-26ffea4d/run.json"
OUTPUT = ROOT / "docs/result_grid.png"


def load_rows():
    run = json.loads(RUN.read_text())
    episodes = [
        json.loads(line)
        for line in RUN.with_name("episodes.jsonl").read_text().splitlines()
        if line.strip()
    ]
    task_ids = sorted(run["tasks"])
    if len(task_ids) != 12 or len(episodes) != 12:
        raise ValueError("Expected 12 tasks and one episode per task.")
    by_task = {episode["task_id"]: episode for episode in episodes}
    if set(by_task) != set(task_ids):
        raise ValueError("Episode task IDs do not match the run manifest.")

    rows = []
    for task_id in task_ids:
        episode = by_task[task_id]
        if episode["run_id"] != run["run_id"] or episode["status"] != "complete":
            raise ValueError(f"Incomplete or mismatched episode: {task_id}")
        if not episode["visible"]["passed"]:
            raise ValueError(f"Figure title requires visible tests to pass: {task_id}")
        hidden = episode["hidden"]["passed"]
        flagged = episode["review"]["flagged"]
        revision = episode["revision"]
        # A fix is a hidden-test failure becoming a pass, without visible regression.
        # Initially passing tasks have no hidden-test-confirmed defect to fix.
        fixed = None
        if not hidden:
            fixed = bool(
                revision["triggered"]
                and revision.get("visible", {}).get("passed", False)
                and revision.get("hidden", {}).get("passed", False)
            )
        bug = not hidden
        correct = flagged == bug
        rows.append((task_id, [bug, correct, fixed]))
    rows.sort(key=lambda row: (0 if row[1][0] else 1 if not row[1][1] else 2, row[0]))
    return run, rows


def main():
    run, rows = load_rows()
    fig, ax = plt.subplots(figsize=(11, 8.5), facecolor="white")
    fig.subplots_adjust(left=0.27, right=0.97, top=0.80, bottom=0.19)
    green, red = "#23835B", "#B84040"
    labels = [
        {True: "Yes", False: "No"},
        {True: "Correct", False: "False alarm"},
        {True: "Fixed", False: "Not fixed"},
    ]

    for row, (task_id, values) in enumerate(rows):
        ax.text(-0.10, row, task_id, ha="right", va="center", fontsize=11)
        for col, value in enumerate(values):
            if value is None:
                continue
            good = not value if col == 0 else value
            label = labels[col][value]
            if col == 1 and not value and values[0]:
                label = "Missed bug"
            ax.add_patch(Rectangle(
                (col, row - 0.46), 0.96, 0.92,
                facecolor=green if good else red, edgecolor="white", linewidth=1,
            ))
            ax.text(
                col + 0.48, row, label, ha="center", va="center",
                fontsize=11, color="white",
            )

    headers = [
        "hidden bug in solution", "reviewer verdict", "fixed after revision",
    ]
    for col, header in enumerate(headers):
        ax.text(col + 0.48, -0.85, header, ha="center", va="bottom", fontsize=10)
    ax.set(xlim=(0, 3), ylim=(len(rows) - 0.45, -0.55))
    ax.set_axis_off()
    fig.text(
        0.06, 0.96,
        "Tests passed on all 12; two hid bugs;\nreview caught both, fixed one.",
        fontsize=21, weight="bold", va="top",
    )
    fig.text(
        0.06, 0.855, "27 September 2026 · 12 tasks · one episode per task",
        fontsize=12, color="#59616B",
    )
    fig.text(
        0.06, 0.13,
        "Bug = initial hidden-test failure. Verdict = correct or wrong against that hidden-test result.\n"
        "Fixed = an initial hidden-test failure passes both suites after revision.\n"
        "Blank = no initial hidden-test failure; includes roman_to_int, revised after an unconfirmed flag.\n"
        "Its false-alarm label is relative to the hidden tests, which do not cover every spec violation.",
        fontsize=9, linespacing=1.6, color="#414851", va="top",
    )
    fig.text(0.06, 0.015, f"Saved run: {run['run_id']}", fontsize=9, color="#59616B")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=180, facecolor="white")
    plt.close(fig)
    print(OUTPUT)


if __name__ == "__main__":
    main()
