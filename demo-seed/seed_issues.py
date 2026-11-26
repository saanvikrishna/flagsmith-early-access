#!/usr/bin/env python3
"""Idempotent seed script for demo GitHub issues using `gh` CLI.

Uses only the Python 3 standard library. Supports `--dry-run` and `--repo <owner/repo>`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable


LABEL_NAME = "early-access"
LABEL_DESCRIPTION = "Early access feature flag request"
LABEL_COLOR = "0E8A16"

ISSUE_TITLE = "Early access request: Acme -> new_dashboard until 2027-01-15"
ISSUE_BODY = (
    "### Early Access Request\n\n"
    "- **Customer:** acme\n"
    "- **Feature:** new_dashboard\n"
    "- **Environment:** Production\n"
    "- **Until:** 2027-01-15\n"
    "- **Requester:** sales-team\n"
)

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class IssueSeedConfig:
    repo: str
    dry_run: bool


def validate_repo(repo: str) -> list[str]:
    """Validate `<owner/repo>` format."""
    errors: list[str] = []
    if not repo:
        errors.append("--repo <owner/repo> is required.")
    elif not _REPO_PATTERN.match(repo):
        errors.append(f"Invalid --repo '{repo}': expected <owner/repo> format.")
    return errors


def build_label_command(repo: str) -> list[str]:
    """Construct the idempotent `gh label create` command."""
    return [
        "gh",
        "label",
        "create",
        LABEL_NAME,
        "--repo",
        repo,
        "--description",
        LABEL_DESCRIPTION,
        "--color",
        LABEL_COLOR,
        "--force",
    ]


def build_issue_list_command(repo: str) -> list[str]:
    """Construct the `gh issue list` command to check for existing demo issues."""
    return [
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "all",
        "--limit",
        "100",
        "--json",
        "number,title,state",
    ]


def build_issue_create_command(repo: str) -> list[str]:
    """Construct the `gh issue create` command for the demo issue."""
    return [
        "gh",
        "issue",
        "create",
        "--repo",
        repo,
        "--title",
        ISSUE_TITLE,
        "--body",
        ISSUE_BODY,
        "--label",
        LABEL_NAME,
    ]


def build_issue_reopen_command(repo: str, number: int) -> list[str]:
    """Construct the `gh issue reopen` command."""
    return [
        "gh",
        "issue",
        "reopen",
        str(number),
        "--repo",
        repo,
    ]


def print_dry_run_plan(config: IssueSeedConfig) -> None:
    """Print the exact planned `gh` commands in dry-run mode."""
    print(f"[dry-run] Config validated for repo '{config.repo}'.")
    print(f"[dry-run] 1. Ensure label '{LABEL_NAME}': {' '.join(build_label_command(config.repo))}")
    print(f"[dry-run] 2. Check existing issues: {' '.join(build_issue_list_command(config.repo))}")
    print(f"[dry-run] 3. Create if missing: title={ISSUE_TITLE!r}, label={LABEL_NAME!r}")


def _run_gh(
    cmd: list[str],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    proc = runner(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stderr: {(proc.stderr or '').strip()}"
        )
    return (proc.stdout or "").strip()


def seed_issues_live(
    config: IssueSeedConfig,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    """Ensure the `early-access` label and demo issue exist idempotently."""
    _run_gh(build_label_command(config.repo), runner=runner)

    raw_issues = _run_gh(build_issue_list_command(config.repo), runner=runner)
    issues = json.loads(raw_issues) if raw_issues else []
    existing = next((i for i in issues if i.get("title") == ISSUE_TITLE), None)

    if existing is None:
        _run_gh(build_issue_create_command(config.repo), runner=runner)
        print(f"[live] Created demo issue '{ISSUE_TITLE}' in {config.repo}.")
    elif str(existing.get("state", "")).upper() == "CLOSED":
        _run_gh(build_issue_reopen_command(config.repo, int(existing["number"])), runner=runner)
        print(
            f"[live] Reopened existing demo issue #{existing['number']} in {config.repo}."
        )
    else:
        print(
            f"[live] Demo issue #{existing['number']} already open in {config.repo}; skipping."
        )


def parse_args(argv: list[str] | None = None) -> IssueSeedConfig:
    parser = argparse.ArgumentParser(
        description="Idempotent seed script for demo GitHub issues."
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="Target GitHub repository in <owner/repo> format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned gh commands and validate config without mutating GitHub.",
    )
    args = parser.parse_args(argv)
    return IssueSeedConfig(repo=args.repo, dry_run=args.dry_run)


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    errors = validate_repo(config.repo)
    if errors:
        for err in errors:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    if config.dry_run:
        print_dry_run_plan(config)
        return 0

    seed_issues_live(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
