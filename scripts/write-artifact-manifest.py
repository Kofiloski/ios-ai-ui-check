#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import mimetypes
import os
from pathlib import Path


KNOWN_ARTIFACTS = (
    ("summary", "report", "Top-level action summary", "summary_path"),
    ("scenario", "scenario", "Resolved scenario JSON", "scenario_path"),
    ("video", "video", "Simulator video recording", "video_path"),
    ("failure-screenshot", "image", "Failure screenshot extracted from xcresult", "failure_screenshot_path"),
    ("before-planning-ui-tree", "inspect", "UI tree captured before AI planning", "before_planning_ui_tree_path"),
    ("before-planning-screenshot", "inspect", "Screenshot captured before AI planning", "before_planning_screenshot_path"),
    ("planner-note", "planner", "Planner note about narrowed or safer route", "planner_note_path"),
    ("planner-request", "planner", "Planner request summary", "planner_request_path"),
    ("planner-response", "planner", "Planner raw response artifact", "planner_response_path"),
    ("planner-validation-error", "planner", "Planner validation error report", "planner_validation_error_path"),
    ("planner-summary", "planner", "Planner summary", "planner_summary_path"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a machine-readable manifest for ios-ai-ui-check artifacts."
    )
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--status", default="")
    parser.add_argument("--resolved-source", default="")
    parser.add_argument("--failure-note", default="")
    for _, _, _, argument_name in KNOWN_ARTIFACTS:
        parser.add_argument(f"--{argument_name.replace('_', '-')}", default="")
    return parser.parse_args()


def infer_category(path: Path) -> str:
    if path.suffix == ".md":
        return "report"
    if path.suffix == ".json":
        return "json"
    if path.suffix in {".png", ".jpg", ".jpeg"}:
        return "image"
    if path.suffix in {".mp4", ".mov"}:
        return "video"
    if path.suffix == ".xcresult":
        return "xcresult"
    if path.suffix in {".txt", ".log", ".env"}:
        return "log"
    return "other"


def media_type_for(path: Path) -> str:
    if path.is_dir() and path.suffix == ".xcresult":
        return "application/vnd.apple.xcresult"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def relative_to_artifacts_dir(artifacts_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(artifacts_dir.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def build_entry(
    *,
    key: str,
    category: str,
    description: str,
    artifacts_dir: Path,
    path: Path,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "key": key,
        "category": category,
        "description": description,
        "relative_path": relative_to_artifacts_dir(artifacts_dir, path),
        "kind": "directory" if path.is_dir() else "file",
        "media_type": media_type_for(path),
    }
    if path.is_file():
        entry["size_bytes"] = path.stat().st_size
    elif path.is_dir():
        entry["entry_count"] = sum(1 for _ in path.iterdir())
    return entry


def build_manifest(
    *,
    artifacts_dir: Path,
    output_path: Path,
    status: str,
    resolved_source: str,
    failure_note: str,
    known_paths: dict[str, Path | None],
) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    primary_artifacts: dict[str, str] = {}
    tracked_relatives: set[str] = set()

    for key, category, description, argument_name in KNOWN_ARTIFACTS:
        candidate = known_paths.get(argument_name)
        if candidate is None or not candidate.exists():
            continue
        entry = build_entry(
            key=key,
            category=category,
            description=description,
            artifacts_dir=artifacts_dir,
            path=candidate,
        )
        entries.append(entry)
        relative_path = entry["relative_path"]
        assert isinstance(relative_path, str)
        primary_artifacts[key] = relative_path
        tracked_relatives.add(relative_path)

    output_relative = relative_to_artifacts_dir(artifacts_dir, output_path)
    for path in sorted(artifacts_dir.rglob("*")):
        if not path.exists():
            continue
        relative_path = relative_to_artifacts_dir(artifacts_dir, path)
        if relative_path == output_relative:
            continue
        if ".sb-" in path.name:
            continue
        if relative_path in tracked_relatives:
            continue

        entries.append(
            build_entry(
                key=f"extra:{relative_path}",
                category=infer_category(path),
                description="Additional artifact discovered in the artifacts directory",
                artifacts_dir=artifacts_dir,
                path=path,
            )
        )

    entries.sort(key=lambda entry: (str(entry["category"]), str(entry["relative_path"])))
    generated_at = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    return {
        "schema_version": 1,
        "tool": "ios-ai-ui-check",
        "generated_at_utc": generated_at,
        "status": status,
        "resolved_source": resolved_source,
        "failure_note": failure_note,
        "artifacts_dir": ".",
        "primary_artifacts": primary_artifacts,
        "artifacts": entries,
    }


def write_github_output(*, output_path: Path) -> None:
    raw_value = os.environ.get("GITHUB_OUTPUT")
    if not raw_value:
        return
    github_output = Path(raw_value)
    with github_output.open("a", encoding="utf-8") as handle:
        handle.write(f"artifact-manifest-path={output_path}\n")


def main() -> int:
    args = parse_args()
    artifacts_dir = args.artifacts_dir.expanduser().resolve()
    output_path = (
        args.output_path.expanduser().resolve()
        if args.output_path is not None
        else (artifacts_dir / "manifest.json")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    known_paths = {
        argument_name: (
            Path(getattr(args, argument_name)).expanduser().resolve()
            if getattr(args, argument_name)
            else None
        )
        for _, _, _, argument_name in KNOWN_ARTIFACTS
    }
    manifest = build_manifest(
        artifacts_dir=artifacts_dir,
        output_path=output_path,
        status=args.status,
        resolved_source=args.resolved_source,
        failure_note=args.failure_note,
        known_paths=known_paths,
    )
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_github_output(output_path=output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
