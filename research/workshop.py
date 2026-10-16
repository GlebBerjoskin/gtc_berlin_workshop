"""Notebook helpers for the GTC Berlin workshop.

Runs go through `openshell/run.py` exactly like the course notebook, but in the
background: the notebook stays free, build and agent logs go to a file, and
`show()` renders the brief instead of thousands of log lines.

    from workshop import prepare, start, status, show
    prepare()
    start('clean', 'Brief me for a call with ...')
    status()
    show('clean')

Standard library only, plus IPython for rendering. Runs outside the sandbox.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
LOGS = PROJECT / "runs" / "_logs"
LABEL_PATTERN = re.compile(r"^[a-z][a-z0-9]{0,5}$")
MODEL_CALL = "POST https://api.studio.nebius.ai/v1/chat/completions"

_processes: dict[str, subprocess.Popen] = {}


def _display(markdown: str) -> None:
    try:
        from IPython.display import Markdown, display
    except ImportError:
        print(markdown)
    else:
        display(Markdown(markdown))


def _duration(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes} min {seconds:02d} s" if minutes else f"{seconds} s"


def prepare() -> None:
    """Register the API keys with OpenShell and build the agent image once."""
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / "prepare.log"
    started = time.monotonic()
    with log.open("w") as output:
        for command in ("setup", "build"):
            result = subprocess.run(
                [sys.executable, "openshell/run.py", command],
                cwd=PROJECT, stdout=output, stderr=subprocess.STDOUT, text=True,
            )
            if result.returncode != 0:
                print(f"{command} failed. Last lines of {log}:\n")
                print("\n".join(log.read_text().splitlines()[-20:]))
                return
    print(f"Ready in {_duration(time.monotonic() - started)}.")


def start(label: str, question: str, *, keep_sandbox: bool = False) -> str:
    """Start one agent run in the background and return its name.

    `label` is a short lowercase word such as 'clean' or 'messy'. Start runs a
    minute apart: each one refreshes the OpenShell providers when it begins.
    """
    if not LABEL_PATTERN.fullmatch(label):
        raise ValueError("label: 1-6 lowercase letters or digits, starting with a letter")
    LOGS.mkdir(parents=True, exist_ok=True)
    name = f"{label}-{datetime.now():%H%M%S}"
    command = [sys.executable, "openshell/run.py", "run", "--name", name]
    if not keep_sandbox:
        command.append("--delete")
    command.append(question)

    (LOGS / f"{name}.json").write_text(json.dumps(
        {"name": name, "label": label, "question": question, "started": time.time()}
    ))
    with (LOGS / f"{name}.log").open("w") as output:
        _processes[name] = subprocess.Popen(
            command, cwd=PROJECT, stdout=output, stderr=subprocess.STDOUT,
            text=True, start_new_session=True,
        )
    print(f"Started {name}. Check it with status(), read it with show('{label}').")
    return name


def _latest(label_or_name: str) -> str:
    if (LOGS / f"{label_or_name}.json").exists():
        return label_or_name
    names = sorted(path.stem for path in LOGS.glob(f"{label_or_name}-*.json"))
    if not names:
        raise ValueError(f"No run called {label_or_name!r}. Start one with start().")
    return names[-1]


def _state(name: str) -> dict:
    meta = json.loads((LOGS / f"{name}.json").read_text())
    log_path = LOGS / f"{name}.log"
    log = log_path.read_text(errors="replace") if log_path.exists() else ""
    run_dir = re.search(r"^Local run: (.+)$", log, re.M)
    process = _processes.get(name)
    if process is not None and process.poll() is None:
        state = "running"
    elif run_dir:
        state = "done"
    elif process is None and time.time() - log_path.stat().st_mtime < 120:
        state = "running"  # started before a kernel restart, still writing
    else:
        state = "failed"
    finished = time.time() if state == "running" else log_path.stat().st_mtime
    return {
        **meta,
        "state": state,
        "elapsed": finished - meta["started"],
        "model_calls": log.count(MODEL_CALL),
        "run_dir": Path(run_dir.group(1).strip()) if run_dir else None,
        "log": log,
    }


def _searches(run_dir: Path | None) -> int | None:
    calls = run_dir / "tool_calls.jsonl" if run_dir else None
    if calls is None or not calls.exists():
        return None
    return sum(1 for line in calls.read_text().splitlines() if line.strip())


def _summary(state: dict) -> str:
    parts = [_duration(state["elapsed"]), f"{state['model_calls']} model calls"]
    searches = _searches(state["run_dir"])
    if searches is not None:
        parts.append(f"{searches} searches")
    return " · ".join(parts)


def status() -> None:
    """One line per run: state, time, model calls, searches."""
    names = sorted(path.stem for path in LOGS.glob("*-*.json")) if LOGS.exists() else []
    if not names:
        print("No runs yet.")
    for name in names:
        state = _state(name)
        print(f"{name:<14} {state['state']:<8} {_summary(state)}")


def show(label_or_name: str, file: str = "final.md") -> None:
    """Render the brief (or another run file, e.g. 'plan.md') of the latest run."""
    state = _state(_latest(label_or_name))
    if state["state"] == "running":
        print(f"{state['name']} is still running: {_summary(state)}")
        return
    if state["state"] == "failed" or state["run_dir"] is None:
        print(f"{state['name']} failed after {_duration(state['elapsed'])}. Last lines of the log:\n")
        print("\n".join(state["log"].splitlines()[-25:]))
        return
    path = state["run_dir"] / file
    if not path.exists():
        files = sorted(str(p.relative_to(state["run_dir"])) for p in state["run_dir"].rglob("*") if p.is_file())
        print(f"No {file} in this run. Files: {', '.join(files) or 'none'}")
        return
    _display(f"**{state['name']}** · {_summary(state)}\n\n---\n\n{path.read_text()}")


def log(label_or_name: str, lines: int = 40) -> None:
    """Print the last lines of a run's log, without the image build."""
    state = _state(_latest(label_or_name))
    agent_lines = [line for line in state["log"].splitlines() if not line.startswith("#")]
    print("\n".join(agent_lines[-lines:]))
