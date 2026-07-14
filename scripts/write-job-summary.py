#!/usr/bin/env python3
"""Append a bounded, UTF-8-safe iOS AI UI Check job summary."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


MAX_SUMMARY_BYTES = 900_000
TRUNCATION_NOTICE = (
    "\n\n_Full summary truncated to fit GitHub's job-summary limit. "
    "See the uploaded artifact when available._\n"
)


def bounded_summary(
    *,
    status: str,
    summary_path: Path | None,
    artifact_url: str,
) -> bytes:
    prefix = f"## iOS AI UI Check\n\nStatus: `{status or 'unknown'}`\n\n"
    if artifact_url:
        prefix += f"Artifact: [ios-ai-ui-check]({artifact_url})\n\n"

    if summary_path is not None and summary_path.is_file():
        summary = summary_path.read_text(encoding="utf-8", errors="replace")
    else:
        summary = "No summary was generated.\n"

    complete = (prefix + summary.rstrip() + "\n").encode("utf-8")
    if len(complete) <= MAX_SUMMARY_BYTES:
        return complete

    prefix_bytes = prefix.encode("utf-8")
    notice_bytes = TRUNCATION_NOTICE.encode("utf-8")
    available = max(0, MAX_SUMMARY_BYTES - len(prefix_bytes) - len(notice_bytes))
    truncated = summary.encode("utf-8")[:available].decode("utf-8", errors="ignore")
    return prefix_bytes + truncated.rstrip().encode("utf-8") + notice_bytes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", default="unknown")
    parser.add_argument("--summary-path", default="")
    parser.add_argument("--artifact-url", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not output_path:
        raise SystemExit("GITHUB_STEP_SUMMARY is not available")

    summary_path = Path(args.summary_path) if args.summary_path else None
    body = bounded_summary(
        status=args.status,
        summary_path=summary_path,
        artifact_url=args.artifact_url,
    )
    with Path(output_path).open("ab") as output:
        output.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
