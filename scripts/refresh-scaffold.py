#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import NoReturn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh an app repo scaffold from .github/ai-ui/scaffold-manifest.json."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Path to the app repository root. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=Path(".github/ai-ui/scaffold-manifest.json"),
        help="Path to the scaffold manifest, relative to --repo-root unless absolute.",
    )
    parser.add_argument(
        "--refresh-customizable-files",
        action="store_true",
        help="Also refresh planner-context and scenario files. By default existing customizable files are preserved.",
    )
    parser.add_argument(
        "--dry-run",
        "--preview",
        action="store_true",
        help="Preview the refresh without writing changes.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable report. If a refresh is executed, captured stdout/stderr are embedded in the report.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not replay the scaffold. Exit 0 when no scaffold drift is detected, otherwise exit 1.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    manifest_path = args.manifest_path
    if not manifest_path.is_absolute():
        manifest_path = repo_root / manifest_path
    manifest_path = manifest_path.resolve()

    manifest = load_manifest(manifest_path)
    command = build_command(
        repo_root=repo_root,
        manifest=manifest,
        dry_run=args.dry_run,
        refresh_customizable_files=args.refresh_customizable_files,
    )
    local_modifications = collect_local_modifications(repo_root=repo_root, manifest=manifest)
    report = build_report(
        repo_root=repo_root,
        manifest_path=manifest_path,
        manifest=manifest,
        refresh_customizable_files=args.refresh_customizable_files,
        dry_run=args.dry_run,
        check_only=args.check,
        command=command,
        local_modifications=local_modifications,
    )

    if args.check:
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print_report(report)
        return check_exit_code(report)

    if args.json:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        report["scaffold"] = {
            "executed": True,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return completed.returncode

    print_report(report)
    subprocess.run(command, check=True)
    return 0


def load_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        fail(f"Scaffold manifest not found: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"Scaffold manifest is not valid JSON: {exc}")

    if not isinstance(payload, dict):
        fail("Scaffold manifest must be a JSON object.")
    if payload.get("tool") != "ios-ai-ui-check":
        fail("Scaffold manifest does not belong to ios-ai-ui-check.")
    return payload


def build_command(
    *,
    repo_root: Path,
    manifest: dict[str, object],
    dry_run: bool,
    refresh_customizable_files: bool,
) -> list[str]:
    script_path = Path(__file__).resolve().parent / "scaffold-app-repo.py"
    command = [
        sys.executable,
        str(script_path),
        "--repo-root",
        str(repo_root),
        "--project",
        required_string(manifest, "project_path"),
        "--scheme",
        required_string(manifest, "scheme"),
        "--scenario-file-name",
        Path(required_string(manifest, "scenario_path")).name,
        "--simulator-name",
        required_string(manifest, "simulator_name"),
        "--simulator-runtime",
        required_string(manifest, "simulator_runtime"),
    ]

    optional_string(manifest, "app_target", command, "--app-target")
    optional_string(manifest, "ui_test_target", command, "--ui-test-target")
    optional_template_path(
        manifest,
        "scenario_template",
        command,
        "--scenario-template",
        repo_root=repo_root,
    )
    optional_template_path(
        manifest,
        "planner_context_template",
        command,
        "--planner-context-template",
        repo_root=repo_root,
    )

    if manifest.get("workflow_generated") is False:
        command.append("--skip-workflow")
    if not refresh_customizable_files:
        command.append("--preserve-customizable-files")
    if dry_run:
        command.append("--dry-run")

    return command


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def collect_local_modifications(
    *,
    repo_root: Path,
    manifest: dict[str, object],
) -> dict[str, object]:
    file_hashes = manifest.get("file_hashes")
    if not isinstance(file_hashes, dict) or not file_hashes:
        return {"status": "unavailable", "changes": []}

    managed_files = set(string_list(manifest.get("managed_files")))
    customizable_files = set(string_list(manifest.get("customizable_files")))
    changes: list[dict[str, str]] = []

    for relative_path in sorted(file_hashes):
        expected_hash = file_hashes[relative_path]
        if not isinstance(expected_hash, str) or not expected_hash:
            continue

        current_path = repo_root / relative_path
        if not current_path.exists():
            state = "missing"
        else:
            current_hash = sha256_bytes(current_path.read_bytes())
            if current_hash == expected_hash:
                continue
            state = "modified"

        if relative_path in managed_files:
            bucket = "managed"
        elif relative_path in customizable_files:
            bucket = "customizable"
        else:
            bucket = "generated"

        changes.append(
            {
                "relative_path": relative_path,
                "state": state,
                "bucket": bucket,
            }
        )

    return {"status": "available", "changes": changes}


def build_check_result(local_modifications: dict[str, object]) -> dict[str, object]:
    status = local_modifications.get("status")
    changes = local_modifications.get("changes")
    if status != "available":
        return {
            "ok": False,
            "reason": "manifest predates content hashes",
            "change_count": 0,
        }
    if not isinstance(changes, list):
        return {
            "ok": False,
            "reason": "local modification report was malformed",
            "change_count": 0,
        }
    if changes:
        return {
            "ok": False,
            "reason": "local scaffold modifications detected",
            "change_count": len(changes),
        }
    return {
        "ok": True,
        "reason": "no scaffold drift detected",
        "change_count": 0,
    }


def build_report(
    *,
    repo_root: Path,
    manifest_path: Path,
    manifest: dict[str, object],
    refresh_customizable_files: bool,
    dry_run: bool,
    check_only: bool,
    command: list[str],
    local_modifications: dict[str, object],
) -> dict[str, object]:
    mode = "check" if check_only else "dry-run" if dry_run else "apply"
    return {
        "tool": "ios-ai-ui-check",
        "repo_root": str(repo_root),
        "manifest_path": str(manifest_path),
        "source_commit": manifest.get("source_commit", "unknown"),
        "refresh_customizable_files": refresh_customizable_files,
        "mode": mode,
        "command": command,
        "local_modifications": local_modifications,
        "check_result": build_check_result(local_modifications),
        "scaffold": {
            "executed": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
        },
    }


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, str) and entry]


def print_local_modifications(
    *,
    report: dict[str, object],
    refresh_customizable_files: bool,
) -> None:
    status = report.get("status")
    if status != "available":
        print("- Local scaffold modifications: unavailable (manifest predates content hashes)")
        return

    changes = report.get("changes")
    if not isinstance(changes, list) or not changes:
        print("- Local scaffold modifications: none detected")
        return

    print("- Local scaffold modifications:")
    for change in changes:
        if not isinstance(change, dict):
            continue
        relative_path = change.get("relative_path")
        state = change.get("state")
        bucket = change.get("bucket")
        if not isinstance(relative_path, str) or not isinstance(state, str) or not isinstance(bucket, str):
            continue
        effect = "will be overwritten"
        if bucket == "customizable" and not refresh_customizable_files:
            effect = "will be preserved"
        print(f"  - {bucket} {state}: {relative_path} ({effect})")


def print_report(report: dict[str, object]) -> None:
    mode = report.get("mode", "apply")
    heading = "Checking ios-ai-ui-check scaffold:" if mode == "check" else "Refreshing ios-ai-ui-check scaffold:"
    print(heading)
    print(f"- Repo root: {report.get('repo_root')}")
    print(f"- Manifest: {report.get('manifest_path')}")
    print(f"- Source commit: {report.get('source_commit', 'unknown')}")
    refresh_customizable_files = bool(report.get("refresh_customizable_files"))
    print(
        f"- Customizable files: {'refreshing' if refresh_customizable_files else 'preserving existing files'}"
    )
    print(f"- Mode: {mode}")
    local_modifications = report.get("local_modifications")
    if isinstance(local_modifications, dict):
        print_local_modifications(
            report=local_modifications,
            refresh_customizable_files=refresh_customizable_files,
        )
    check_result = report.get("check_result")
    if mode == "check" and isinstance(check_result, dict):
        outcome = "clean" if check_result.get("ok") else "drift detected"
        print(f"- Check result: {outcome} ({check_result.get('reason', 'unknown')})")


def check_exit_code(report: dict[str, object]) -> int:
    check_result = report.get("check_result")
    if not isinstance(check_result, dict):
        return 1
    return 0 if check_result.get("ok") else 1


def required_string(manifest: dict[str, object], key: str) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or not value:
        fail(f"Scaffold manifest is missing required string field '{key}'.")
    return value


def optional_string(
    manifest: dict[str, object],
    key: str,
    command: list[str],
    flag: str,
) -> None:
    value = manifest.get(key)
    if isinstance(value, str) and value:
        command.extend([flag, value])


def optional_template_path(
    manifest: dict[str, object],
    key: str,
    command: list[str],
    flag: str,
    *,
    repo_root: Path,
) -> None:
    value = manifest.get(key)
    if not isinstance(value, str) or not value:
        return
    template_path = Path(value).expanduser()
    if not template_path.is_absolute():
        template_path = repo_root / template_path
    command.extend([flag, str(template_path.resolve())])


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
