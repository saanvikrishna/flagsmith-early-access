#!/usr/bin/env python3
"""Idempotent seed script for the early-access-demo Flagsmith project.

Uses only the Python 3 standard library and shells out to Flagsmith CLI v2.0.0
(`flagsmith api`). Supports `--dry-run` and `--mode live`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable


PROJECT_NAME = "early-access-demo"
ENVIRONMENTS = ("Production", "Development")
FEATURES = ("new_dashboard", "ai_summaries", "bulk_export")

IDENTITIES: tuple[dict[str, str], ...] = (
    {"identifier": "user_1", "org_id": "acme", "plan": "enterprise"},
    {"identifier": "user_2", "org_id": "acme", "plan": "enterprise"},
    {"identifier": "user_3", "org_id": "globex", "plan": "pro"},
    {"identifier": "user_4", "org_id": "globex", "plan": "pro"},
    {"identifier": "user_5", "org_id": "initech", "plan": "starter"},
    {"identifier": "user_42", "org_id": "initech", "plan": "starter"},
)

EXPIRED_EA_SEGMENT = {
    "name": "ea-bulk_export-initech",
    "description": (
        "early-access; flag=bulk_export; customer=initech; "
        "expires=2026-11-25; issue=seed"
    ),
    "org_id": "initech",
    "feature": "bulk_export",
    "enabled": True,
}

INTERNAL_SEGMENT = {
    "name": "internal_staff",
    "description": "Internal staff dogfooding segment (non-early-access)",
    "org_id": "internal",
    "feature": "ai_summaries",
    "enabled": True,
}


@dataclass(frozen=True)
class SeedConfig:
    mode: str
    project: str
    api_key: str
    environment: str
    organisation: str


def build_segment_payload(
    *,
    name: str,
    description: str,
    project_id: int,
    org_id: str,
) -> dict[str, Any]:
    """Build a Flagsmith segment payload matching `org_id == <org_id>`."""
    return {
        "name": name,
        "description": description,
        "project": project_id,
        "rules": [
            {
                "type": "ALL",
                "rules": [
                    {
                        "type": "ANY",
                        "conditions": [
                            {
                                "operator": "EQUAL",
                                "property": "org_id",
                                "value": org_id,
                            }
                        ],
                    }
                ],
                "conditions": [],
            }
        ],
    }


def build_identity_payload(identity: dict[str, str]) -> dict[str, Any]:
    """Build a Flagsmith SDK identity+traits upsert payload."""
    return {
        "identifier": identity["identifier"],
        "traits": [
            {"trait_key": "org_id", "trait_value": identity["org_id"]},
            {"trait_key": "plan", "trait_value": identity["plan"]},
        ],
    }


def validate_config(config: SeedConfig) -> list[str]:
    """Validate seed configuration and return any validation errors."""
    errors: list[str] = []
    if not config.project:
        errors.append("Project name must not be empty.")
    if config.mode == "live":
        if not config.api_key:
            errors.append("FLAGSMITH_API_KEY is required in --mode live.")
        if not config.environment:
            errors.append("FLAGSMITH_ENVIRONMENT is required in --mode live.")
    return errors


def _extract_results(data: Any) -> list[dict[str, Any]]:
    """Handle both paginated (`{"results": [...]}`) and list API responses."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data["results"]
    return []


class FlagsmithCLI:
    """Thin wrapper around `flagsmith api` CLI v2.0.0."""

    def __init__(
        self,
        config: SeedConfig,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.config = config
        self.runner = runner

    def api(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        sdk: bool = False,
        env_key: str | None = None,
    ) -> Any:
        resolved_bin = shutil.which("flagsmith") or "flagsmith"
        cmd = [resolved_bin, "api"]
        if sdk:
            cmd.append("--sdk")
        if env_key:
            cmd.extend(["-e", env_key])
        cmd.append(path)
        if method != "GET":
            cmd.extend(["-X", method])

        stdin_text: str | None = None
        if payload is not None:
            cmd.extend(["--input", "-"])
            stdin_text = json.dumps(payload)

        cmd.extend(["--json", "--no-input"])

        env = os.environ.copy()
        if self.config.api_key:
            env["FLAGSMITH_API_KEY"] = self.config.api_key
        if self.config.environment:
            env["FLAGSMITH_ENVIRONMENT"] = self.config.environment
        if self.config.organisation:
            env["FLAGSMITH_ORGANISATION"] = self.config.organisation

        proc = self.runner(
            cmd,
            input=stdin_text,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
                f"stderr: {proc.stderr.strip()}"
            )
        stdout = (proc.stdout or "").strip()
        if not stdout:
            return None
        return json.loads(stdout)


def print_dry_run_plan(config: SeedConfig) -> None:
    """Print the exact planned actions for dry-run mode."""
    print(f"[dry-run] Config validated for project '{config.project}'.")
    if not config.api_key:
        print("[dry-run] Note: FLAGSMITH_API_KEY is not set (ok for dry-run).")
    if not config.environment:
        print("[dry-run] Note: FLAGSMITH_ENVIRONMENT is not set (ok for dry-run).")

    print(f"[dry-run] 1. Resolve project '{config.project}' and environments {list(ENVIRONMENTS)}.")
    print(f"[dry-run] 2. Ensure features exist and are disabled by default: {list(FEATURES)}.")
    print("[dry-run] 3. Remove any existing 'ea-*' segments and overrides.")
    print("[dry-run] 4. Remove any identity-level feature overrides.")
    print(
        "[dry-run] 5. Upsert 6 identities across 3 orgs (acme, globex, initech) "
        "with org_id and plan traits in Production and Development."
    )
    for ident in IDENTITIES:
        print(
            f"[dry-run]    - {ident['identifier']} "
            f"(org_id={ident['org_id']}, plan={ident['plan']})"
        )
    print(
        f"[dry-run] 6. Ensure expired early-access segment '{EXPIRED_EA_SEGMENT['name']}' "
        f"(org_id == {EXPIRED_EA_SEGMENT['org_id']}, description='{EXPIRED_EA_SEGMENT['description']}') "
        f"with override ON for '{EXPIRED_EA_SEGMENT['feature']}'."
    )
    print(
        f"[dry-run] 7. Ensure non-early-access segment '{INTERNAL_SEGMENT['name']}' "
        f"(org_id == {INTERNAL_SEGMENT['org_id']}) "
        f"with override ON for '{INTERNAL_SEGMENT['feature']}'."
    )


def _ensure_segment_with_override(
    cli: FlagsmithCLI,
    *,
    project_id: int,
    env_id: int,
    env_api_key: str,
    feature_id: int,
    spec: dict[str, Any],
    existing_segments: dict[str, dict[str, Any]],
) -> None:
    """Ensure a segment exists with the expected rule and an ON override in env."""
    name = spec["name"]
    if name in existing_segments:
        cli.api(
            f"api/v1/projects/{project_id}/segments/{existing_segments[name]['id']}/",
            method="DELETE",
        )

    seg_payload = build_segment_payload(
        name=name,
        description=spec["description"],
        project_id=project_id,
        org_id=spec["org_id"],
    )
    created_seg = cli.api(
        f"api/v1/projects/{project_id}/segments/",
        method="POST",
        payload=seg_payload,
    )
    seg_id = created_seg["id"]
    existing_segments[name] = created_seg

    resolved_bin = shutil.which("flagsmith") or "flagsmith"
    env = os.environ.copy()
    if cli.config.api_key:
        env["FLAGSMITH_API_KEY"] = cli.config.api_key
    if env_api_key:
        env["FLAGSMITH_ENVIRONMENT"] = env_api_key
    if cli.config.organisation:
        env["FLAGSMITH_ORGANISATION"] = cli.config.organisation
    flag_cmd = [
        resolved_bin,
        "flag",
        "update",
        spec["feature"],
        "--enable" if spec["enabled"] else "--disable",
        "--segment",
        name,
        "--yes",
        "--no-input",
    ]
    proc = cli.runner(flag_cmd, text=True, capture_output=True, check=False, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to set segment override: {proc.stderr.strip()}")


def seed_live(cli: FlagsmithCLI) -> None:
    """Execute idempotent seed against live Flagsmith via `flagsmith api`."""
    projects = _extract_results(cli.api("api/v1/projects/"))
    project = next((p for p in projects if p.get("name") == cli.config.project), None)
    if not project:
        raise RuntimeError(f"Flagsmith project '{cli.config.project}' not found.")
    project_id = project["id"]

    envs = _extract_results(cli.api(f"api/v1/environments/?project={project_id}"))
    env_by_name = {e["name"]: e for e in envs if e.get("name") in ENVIRONMENTS}
    missing_envs = [name for name in ENVIRONMENTS if name not in env_by_name]
    if missing_envs:
        raise RuntimeError(f"Missing environments in project '{cli.config.project}': {missing_envs}")

    # 1. Ensure features exist
    existing_features = {
        f["name"]: f
        for f in _extract_results(cli.api(f"api/v1/projects/{project_id}/features/"))
    }
    feature_ids: dict[str, int] = {}
    for feat_name in FEATURES:
        if feat_name in existing_features:
            feature_ids[feat_name] = existing_features[feat_name]["id"]
        else:
            created = cli.api(
                f"api/v1/projects/{project_id}/features/",
                method="POST",
                payload={"name": feat_name, "type": "STANDARD", "default_enabled": False},
            )
            feature_ids[feat_name] = created["id"]

    # 2. Remove existing ea-* segments and internal_staff (recreated cleanly below)
    segments = _extract_results(cli.api(f"api/v1/projects/{project_id}/segments/"))
    existing_segments: dict[str, dict[str, Any]] = {}
    for seg in segments:
        seg_name = seg.get("name", "")
        if seg_name.startswith("ea-") or seg_name == INTERNAL_SEGMENT["name"]:
            cli.api(
                f"api/v1/projects/{project_id}/segments/{seg['id']}/",
                method="DELETE",
            )
        else:
            existing_segments[seg_name] = seg

    # 3. Reset environment defaults, clean identity overrides, upsert identities
    for env_name in ENVIRONMENTS:
        env_obj = env_by_name[env_name]
        env_key = env_obj["api_key"]

        # Reset default feature states to False and delete any identity overrides
        for feat_name, feat_id in feature_ids.items():
            fstates = _extract_results(
                cli.api(f"api/v1/environments/{env_key}/featurestates/?feature={feat_id}")
            )
            for fs in fstates:
                if fs.get("identity") is not None:
                    cli.api(
                        f"api/v1/environments/{env_key}/featurestates/{fs['id']}/",
                        method="DELETE",
                    )
                elif fs.get("feature_segment") is None and fs.get("enabled") is not False:
                    resolved_bin = shutil.which("flagsmith") or "flagsmith"
                    env = os.environ.copy()
                    if cli.config.api_key:
                        env["FLAGSMITH_API_KEY"] = cli.config.api_key
                    env["FLAGSMITH_ENVIRONMENT"] = env_key
                    if cli.config.organisation:
                        env["FLAGSMITH_ORGANISATION"] = cli.config.organisation
                    proc = cli.runner(
                        [resolved_bin, "flag", "update", feat_name, "--disable", "--yes", "--no-input"],
                        text=True,
                        capture_output=True,
                        check=False,
                        env=env,
                    )
                    if proc.returncode != 0:
                        cli.api(
                            f"api/v1/environments/{env_key}/featurestates/{fs['id']}/",
                            method="PATCH",
                            payload={"enabled": False},
                        )

        # Upsert identities and traits via Flagsmith CLI evaluate --persist
        resolved_bin = shutil.which("flagsmith") or "flagsmith"
        for ident in IDENTITIES:
            env = os.environ.copy()
            if cli.config.api_key:
                env["FLAGSMITH_API_KEY"] = cli.config.api_key
            env["FLAGSMITH_ENVIRONMENT"] = env_key
            if cli.config.organisation:
                env["FLAGSMITH_ORGANISATION"] = cli.config.organisation
            eval_cmd = [
                resolved_bin,
                "evaluate",
                "--identity",
                ident["identifier"],
                "--trait",
                f"org_id={ident['org_id']}",
                "--trait",
                f"plan={ident['plan']}",
                "--persist",
                "--no-input",
                "--json",
            ]
            proc = cli.runner(eval_cmd, text=True, capture_output=True, check=False, env=env)
            if proc.returncode != 0:
                raise RuntimeError(f"Failed to persist identity {ident['identifier']}: {proc.stderr.strip()}")

    # 4. Create the expired EA segment and internal_staff segment in Production
    prod_env = env_by_name["Production"]
    for spec in (EXPIRED_EA_SEGMENT, INTERNAL_SEGMENT):
        _ensure_segment_with_override(
            cli,
            project_id=project_id,
            env_id=prod_env["id"],
            env_api_key=prod_env["api_key"],
            feature_id=feature_ids[spec["feature"]],
            spec=spec,
            existing_segments=existing_segments,
        )

    print(f"[live] Successfully seeded project '{cli.config.project}'.")


def parse_args(argv: list[str] | None = None) -> SeedConfig:
    parser = argparse.ArgumentParser(
        description="Idempotent seed script for the early-access-demo Flagsmith project."
    )
    parser.add_argument(
        "--mode",
        choices=("dry-run", "live"),
        default="dry-run",
        help="Execution mode (default: dry-run).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions and validate config without mutating Flagsmith.",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("FLAGSMITH_PROJECT", PROJECT_NAME),
        help=f"Flagsmith project name (default: {PROJECT_NAME}).",
    )
    args = parser.parse_args(argv)
    mode = "dry-run" if args.dry_run else args.mode
    return SeedConfig(
        mode=mode,
        project=args.project,
        api_key=os.environ.get("FLAGSMITH_API_KEY", ""),
        environment=os.environ.get("FLAGSMITH_ENVIRONMENT", ""),
        organisation=os.environ.get("FLAGSMITH_ORGANISATION", ""),
    )


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    errors = validate_config(config)
    if errors:
        for err in errors:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    if config.mode == "dry-run":
        print_dry_run_plan(config)
        return 0

    cli = FlagsmithCLI(config)
    seed_live(cli)
    return 0


if __name__ == "__main__":
    sys.exit(main())
