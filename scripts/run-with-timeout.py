#!/usr/bin/env python3
"""Run a command with a timeout and terminate its entire process group."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--termination-grace", type=float, default=5.0)
    parser.add_argument("--label", default="Command")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.termination_grace < 0:
        parser.error("--termination-grace must be zero or greater")
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return args


def signal_process_group(process: subprocess.Popen[bytes], signal_number: int) -> None:
    try:
        os.killpg(process.pid, signal_number)
    except ProcessLookupError:
        return


def process_group_exists(process: subprocess.Popen[bytes]) -> bool:
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_process_group(
    process: subprocess.Popen[bytes],
    *,
    termination_grace: float,
) -> None:
    signal_process_group(process, signal.SIGTERM)
    deadline = time.monotonic() + termination_grace
    while process_group_exists(process) and time.monotonic() < deadline:
        if process.poll() is None:
            try:
                process.wait(timeout=min(0.05, max(0.0, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                pass
        else:
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    if process_group_exists(process):
        signal_process_group(process, signal.SIGKILL)

    if process.poll() is None:
        process.wait()


def conventional_exit_code(return_code: int) -> int:
    """Map subprocess signal return codes to the conventional shell status."""

    if return_code < 0:
        return 128 + abs(return_code)
    return return_code


def main() -> int:
    args = parse_args()
    process = subprocess.Popen(args.command, start_new_session=True)
    cleaning_up = False

    def forward_signal(signal_number: int, _frame: object) -> None:
        signal_process_group(process, signal_number)
        if not cleaning_up:
            raise SystemExit(128 + signal_number)

    signal.signal(signal.SIGINT, forward_signal)
    signal.signal(signal.SIGTERM, forward_signal)

    try:
        return conventional_exit_code(process.wait(timeout=args.timeout))
    except subprocess.TimeoutExpired:
        print(
            f"{args.label} timed out after {args.timeout:g} seconds",
            file=sys.stderr,
        )
        return 124
    finally:
        cleaning_up = True
        if process_group_exists(process):
            stop_process_group(
                process,
                termination_grace=args.termination_grace,
            )


if __name__ == "__main__":
    raise SystemExit(main())
