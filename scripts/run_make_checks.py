"""Run Makefile check targets with progress and ordered logs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import time


@dataclass(frozen=True)
class CheckSpec:
    target: str
    label: str


@dataclass
class RunningCheck:
    spec: CheckSpec
    log_path: Path
    process: subprocess.Popen[bytes]
    started_at: float
    finished_at: float | None = None
    exit_code: int | None = None

    @property
    def elapsed(self) -> float:
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return end - self.started_at


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--title",
        default="checks",
        help="Short name used in the progress output and log directory.",
    )
    parser.add_argument(
        "--log-root",
        default=None,
        help="Directory where per-target logs are stored.",
    )
    parser.add_argument(
        "--progress-interval",
        default=5.0,
        type=float,
        help="Seconds between progress updates while checks are still running.",
    )
    parser.add_argument(
        "targets",
        nargs="+",
        help="Make targets to run. Use target=Label for a friendlier display label.",
    )
    return parser.parse_args()


def _check_specs(raw_targets: list[str]) -> list[CheckSpec]:
    specs: list[CheckSpec] = []
    for raw in raw_targets:
        target, sep, label = raw.partition("=")
        specs.append(CheckSpec(target=target, label=label if sep else target))
    return specs


def _log_dir(title: str, log_root: str | None) -> Path:
    root = (
        Path(log_root)
        if log_root
        else Path(os.environ.get("DASHBOARD_STATE_DIR", ".cache/todoist-assistant/dashboard"))
        / "checks"
    )
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = root / f"{timestamp}-{title.replace(' ', '_')}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _start_check(spec: CheckSpec, log_dir: Path) -> RunningCheck:
    log_path = log_dir / f"{spec.target}.log"
    log_handle = log_path.open("wb")
    try:
        process = subprocess.Popen(
            [os.environ.get("MAKE", "make"), "--no-print-directory", spec.target],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
    except Exception:
        log_handle.close()
        raise
    log_handle.close()
    return RunningCheck(
        spec=spec,
        log_path=log_path,
        process=process,
        started_at=time.monotonic(),
    )


def _status_word(exit_code: int) -> str:
    return "passed" if exit_code == 0 else "failed"


def _print_progress(checks: list[RunningCheck], completed: int) -> None:
    total = len(checks)
    states = []
    for check in checks:
        if check.exit_code is None:
            states.append(f"{check.spec.label}: running {check.elapsed:.1f}s")
        else:
            states.append(
                f"{check.spec.label}: {_status_word(check.exit_code)} {check.elapsed:.1f}s"
            )
    print(f"Progress [{completed}/{total}] " + " | ".join(states), flush=True)


def _print_logs(checks: list[RunningCheck]) -> None:
    for check in checks:
        exit_code = check.exit_code if check.exit_code is not None else 1
        print(
            f"\n===== {check.spec.label} ({_status_word(exit_code)}, {check.elapsed:.1f}s) =====",
            flush=True,
        )
        try:
            text = check.log_path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            print(f"Log missing: {check.log_path}")
            text = ""
        sys.stdout.write(text)
        if text and not text.endswith("\n"):
            print()
        print(f"===== {check.spec.label} exit {exit_code} =====", flush=True)


def main() -> int:
    args = _parse_args()
    specs = _check_specs(args.targets)
    log_dir = _log_dir(str(args.title), args.log_root)
    print(f"Running {args.title}: {', '.join(spec.label for spec in specs)}", flush=True)
    print(f"Logs: {log_dir}", flush=True)

    checks = [_start_check(spec, log_dir) for spec in specs]
    completed = 0
    _print_progress(checks, completed)

    last_progress_at = time.monotonic()
    while completed < len(checks):
        changed = False
        for check in checks:
            if check.exit_code is not None:
                continue
            exit_code = check.process.poll()
            if exit_code is None:
                continue
            check.finished_at = time.monotonic()
            check.exit_code = exit_code
            completed += 1
            changed = True
            print(
                f"Completed [{completed}/{len(checks)}] {check.spec.label}: "
                f"{_status_word(exit_code)} (exit {exit_code}, {check.elapsed:.1f}s)",
                flush=True,
            )
        if completed < len(checks):
            if not changed:
                time.sleep(min(args.progress_interval, 1.0))
            now = time.monotonic()
            if changed or now - last_progress_at >= args.progress_interval:
                _print_progress(checks, completed)
                last_progress_at = now

    _print_logs(checks)
    worst_exit = max((check.exit_code or 0) for check in checks)
    print(f"\nLogs kept in {log_dir}", flush=True)
    print(f"{args.title} {_status_word(worst_exit)}.", flush=True)
    return worst_exit


if __name__ == "__main__":
    raise SystemExit(main())
