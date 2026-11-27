#!/usr/bin/env python3
"""Bootstrap script for the self-hosted open-source Flagsmith stack.

Uses only the Python 3 standard library. Waits for Flagsmith health,
registers/logs in the demo admin user, provisions the organisation, project,
and Admin API token, writes `.env`, and seeds the demo flags, segments,
segment overrides, and identities.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ADMIN_EMAIL = "admin@early-access.local"
ADMIN_FIRST_NAME = "Early"
ADMIN_LAST_NAME = "Access"
DEFAULT_ADMIN_PASSWORD = os.environ.get(
    "FLAGSMITH_ADMIN_PASSWORD", "EarlyAccessDemo123!"
)
ORG_NAME = "Early Access Demo"
PROJECT_NAME = "early-access-demo"
MASTER_KEY_NAME = "early-access-bootstrap"

FEATURES = ("new_dashboard", "ai_summaries", "bulk_export")

IDENTITIES: tuple[dict[str, str], ...] = (
    {"identifier": "user_1", "org_id": "acme", "plan": "enterprise"},
    {"identifier": "user_2", "org_id": "acme", "plan": "enterprise"},
    {"identifier": "user_3", "org_id": "globex", "plan": "pro"},
    {"identifier": "user_4", "org_id": "globex", "plan": "pro"},
    {"identifier": "user_5", "org_id": "initech", "plan": "starter"},
    {"identifier": "user_42", "org_id": "initech", "plan": "starter"},
)

SEGMENTS: tuple[dict[str, Any], ...] = (
    {
        "name": "ea-bulk_export-initech",
        "description": (
            "early-access; flag=bulk_export; customer=initech; "
            "expires=2026-11-25; issue=seed"
        ),
        "org_id": "initech",
        "feature": "bulk_export",
        "enabled": True,
    },
    {
        "name": "internal_staff",
        "description": "Internal staff dogfooding segment (non-early-access)",
        "org_id": "internal",
        "feature": "ai_summaries",
        "enabled": True,
    },
)


class BootstrapError(RuntimeError):
    """Raised when a Flagsmith API request fails unexpectedly."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: Any


RequestFn = Callable[
    [str, str, dict[str, Any] | None, dict[str, str] | None], HttpResponse
]


def default_http_request(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> HttpResponse:
    """Perform an HTTP JSON request using urllib.request."""
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    data: bytes | None = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw.strip() else None
            return HttpResponse(status=resp.status, body=parsed)
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw.strip() else raw
        except json.JSONDecodeError:
            parsed = raw
        return HttpResponse(status=err.code, body=parsed)
    except urllib.error.URLError as err:
        raise BootstrapError(f"Connection error for {method} {url}: {err.reason}") from err


def extract_results(data: Any) -> list[dict[str, Any]]:
    """Normalize paginated (`{"results": [...]}`) and list API responses."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data["results"]
    return []


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


def wait_for_health(
    base_url: str,
    *,
    request_fn: RequestFn = default_http_request,
    timeout: float = 120.0,
    poll_interval: float = 2.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """Poll GET /health until Flagsmith responds with HTTP 200."""
    health_url = f"{base_url.rstrip('/')}/health"
    deadline = time.monotonic() + timeout
    last_error = "no response"

    while True:
        try:
            resp = request_fn("GET", health_url, None, None)
            if resp.status == 200:
                return
            last_error = f"HTTP {resp.status}"
        except BootstrapError as err:
            last_error = str(err)

        if time.monotonic() >= deadline:
            raise BootstrapError(
                f"Timed out waiting for Flagsmith health at {health_url}: {last_error}"
            )
        sleep_fn(poll_interval)


def ensure_admin_token(
    base_url: str,
    *,
    email: str = ADMIN_EMAIL,
    password: str = DEFAULT_ADMIN_PASSWORD,
    request_fn: RequestFn = default_http_request,
) -> str:
    """Register (if needed) and log in the admin user, returning the auth token."""
    base = base_url.rstrip("/")
    reg_payload = {
        "email": email,
        "first_name": ADMIN_FIRST_NAME,
        "last_name": ADMIN_LAST_NAME,
        "password": password,
        "re_password": password,
    }
    reg_resp = request_fn("POST", f"{base}/api/v1/auth/users/", reg_payload, None)
    if reg_resp.status not in (200, 201, 400):
        raise BootstrapError(
            f"Unexpected status registering admin user: {reg_resp.status} {reg_resp.body}"
        )

    login_resp = request_fn(
        "POST",
        f"{base}/api/v1/auth/login/",
        {"email": email, "password": password},
        None,
    )
    if login_resp.status != 200 or not isinstance(login_resp.body, dict):
        raise BootstrapError(
            f"Failed to log in admin user: {login_resp.status} {login_resp.body}"
        )
    token = login_resp.body.get("key")
    if not token:
        raise BootstrapError("Login response did not include auth 'key'.")
    return str(token)


def ensure_organisation(
    base_url: str,
    auth_headers: dict[str, str],
    *,
    name: str = ORG_NAME,
    request_fn: RequestFn = default_http_request,
) -> dict[str, Any]:
    """Fetch or create the Flagsmith organisation."""
    base = base_url.rstrip("/")
    resp = request_fn("GET", f"{base}/api/v1/organisations/", None, auth_headers)
    if resp.status != 200:
        raise BootstrapError(f"Failed to list organisations: {resp.status} {resp.body}")
    for org in extract_results(resp.body):
        if org.get("name") == name:
            return org

    created = request_fn(
        "POST", f"{base}/api/v1/organisations/", {"name": name}, auth_headers
    )
    if created.status not in (200, 201) or not isinstance(created.body, dict):
        raise BootstrapError(
            f"Failed to create organisation: {created.status} {created.body}"
        )
    return created.body


def ensure_project(
    base_url: str,
    auth_headers: dict[str, str],
    org_id: int,
    *,
    name: str = PROJECT_NAME,
    request_fn: RequestFn = default_http_request,
) -> dict[str, Any]:
    """Fetch or create the Flagsmith project."""
    base = base_url.rstrip("/")
    resp = request_fn(
        "GET",
        f"{base}/api/v1/projects/?organisation={org_id}",
        None,
        auth_headers,
    )
    if resp.status != 200:
        raise BootstrapError(f"Failed to list projects: {resp.status} {resp.body}")
    for proj in extract_results(resp.body):
        if proj.get("name") == name:
            return proj

    created = request_fn(
        "POST",
        f"{base}/api/v1/projects/",
        {"name": name, "organisation": org_id},
        auth_headers,
    )
    if created.status not in (200, 201) or not isinstance(created.body, dict):
        raise BootstrapError(
            f"Failed to create project: {created.status} {created.body}"
        )
    return created.body


def fetch_environments(
    base_url: str,
    auth_headers: dict[str, str],
    project_id: int,
    *,
    request_fn: RequestFn = default_http_request,
) -> dict[str, dict[str, Any]]:
    """Fetch Development and Production environments keyed by name."""
    base = base_url.rstrip("/")
    resp = request_fn(
        "GET",
        f"{base}/api/v1/environments/?project={project_id}",
        None,
        auth_headers,
    )
    if resp.status != 200:
        raise BootstrapError(f"Failed to list environments: {resp.status} {resp.body}")
    envs = {env["name"]: env for env in extract_results(resp.body) if "name" in env}
    for required in ("Development", "Production"):
        if required not in envs:
            raise BootstrapError(f"Missing expected environment: {required}")
    return envs


def create_admin_api_token(
    base_url: str,
    auth_headers: dict[str, str],
    org_id: int,
    fallback_token: str,
    *,
    request_fn: RequestFn = default_http_request,
) -> str:
    """Create an organisation Master API Key, falling back to user auth token."""
    base = base_url.rstrip("/")
    resp = request_fn(
        "POST",
        f"{base}/api/v1/organisations/{org_id}/master-api-keys/",
        {"name": MASTER_KEY_NAME, "organisation": org_id, "is_admin": True},
        auth_headers,
    )
    if resp.status in (200, 201) and isinstance(resp.body, dict) and resp.body.get("key"):
        return str(resp.body["key"])
    return fallback_token


def write_env_file(
    env_path: Path,
    *,
    api_url: str,
    api_key: str,
    prod_env_key: str,
    dev_env_key: str,
) -> Path:
    """Write `.env` with Flagsmith connection and environment variables."""
    base = api_url.rstrip("/")
    lines = [
        f"FLAGSMITH_API_URL={base}",
        f"FLAGSMITH_SDK_API_URL={base}/api/v1/identities/",
        f"FLAGSMITH_API_KEY={api_key}",
        f"FLAGSMITH_ENVIRONMENT={prod_env_key}",
        f"FLAGSMITH_ENV_KEY_PROD={prod_env_key}",
        f"FLAGSMITH_ENV_KEY_DEV={dev_env_key}",
    ]
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path


def seed_demo_data(
    base_url: str,
    auth_headers: dict[str, str],
    project_id: int,
    envs: dict[str, dict[str, Any]],
    *,
    request_fn: RequestFn = default_http_request,
) -> None:
    """Idempotently seed features, segments, segment overrides, and identities."""
    base = base_url.rstrip("/")

    # 1. Features
    feat_resp = request_fn(
        "GET", f"{base}/api/v1/projects/{project_id}/features/", None, auth_headers
    )
    if feat_resp.status != 200:
        raise BootstrapError(
            f"Failed to list features: {feat_resp.status} {feat_resp.body}"
        )
    features_by_name = {
        f["name"]: f for f in extract_results(feat_resp.body) if "name" in f
    }
    for feature_name in FEATURES:
        if feature_name not in features_by_name:
            created = request_fn(
                "POST",
                f"{base}/api/v1/projects/{project_id}/features/",
                {
                    "name": feature_name,
                    "type": "STANDARD",
                    "default_enabled": False,
                },
                auth_headers,
            )
            if created.status not in (200, 201) or not isinstance(created.body, dict):
                raise BootstrapError(
                    f"Failed to create feature {feature_name}: {created.status} {created.body}"
                )
            features_by_name[feature_name] = created.body

    # 2. Segments
    seg_resp = request_fn(
        "GET", f"{base}/api/v1/projects/{project_id}/segments/", None, auth_headers
    )
    if seg_resp.status != 200:
        raise BootstrapError(
            f"Failed to list segments: {seg_resp.status} {seg_resp.body}"
        )
    segments_by_name = {
        s["name"]: s for s in extract_results(seg_resp.body) if "name" in s
    }
    for seg_spec in SEGMENTS:
        if seg_spec["name"] not in segments_by_name:
            payload = build_segment_payload(
                name=seg_spec["name"],
                description=seg_spec["description"],
                project_id=project_id,
                org_id=seg_spec["org_id"],
            )
            created = request_fn(
                "POST",
                f"{base}/api/v1/projects/{project_id}/segments/",
                payload,
                auth_headers,
            )
            if created.status not in (200, 201) or not isinstance(created.body, dict):
                raise BootstrapError(
                    f"Failed to create segment {seg_spec['name']}: {created.status} {created.body}"
                )
            segments_by_name[seg_spec["name"]] = created.body

    # 3. Segment overrides in Production & Development
    for env_name in ("Production", "Development"):
        env = envs[env_name]
        env_key = env["api_key"]
        fs_resp = request_fn(
            "GET",
            f"{base}/api/v1/environments/{env_key}/featurestates/",
            None,
            auth_headers,
        )
        if fs_resp.status != 200:
            raise BootstrapError(
                f"Failed to list featurestates for {env_name}: {fs_resp.status} {fs_resp.body}"
            )
        existing_overrides = {
            (fs.get("feature"), fs.get("feature_segment", {}).get("segment"))
            if isinstance(fs.get("feature_segment"), dict)
            else (fs.get("feature"), fs.get("feature_segment"))
            for fs in extract_results(fs_resp.body)
        }
        for seg_spec in SEGMENTS:
            feature_id = features_by_name[seg_spec["feature"]]["id"]
            segment_id = segments_by_name[seg_spec["name"]]["id"]
            if (feature_id, segment_id) in existing_overrides:
                continue
            override_resp = request_fn(
                "POST",
                f"{base}/api/v1/environments/{env_key}/featurestates/",
                {
                    "feature": feature_id,
                    "feature_segment": {"segment": segment_id},
                    "enabled": seg_spec["enabled"],
                },
                auth_headers,
            )
            if override_resp.status not in (200, 201):
                raise BootstrapError(
                    f"Failed to create segment override in {env_name}: "
                    f"{override_resp.status} {override_resp.body}"
                )

    # 4. Identities & traits via SDK endpoint in Production & Development
    for env_name in ("Production", "Development"):
        env_key = envs[env_name]["api_key"]
        sdk_headers = {"X-Environment-Key": env_key}
        for ident in IDENTITIES:
            payload = {
                "identifier": ident["identifier"],
                "traits": [
                    {"trait_key": "org_id", "trait_value": ident["org_id"]},
                    {"trait_key": "plan", "trait_value": ident["plan"]},
                ],
            }
            id_resp = request_fn(
                "POST",
                f"{base}/api/v1/identities/",
                payload,
                sdk_headers,
            )
            if id_resp.status not in (200, 201):
                raise BootstrapError(
                    f"Failed to upsert identity {ident['identifier']} in {env_name}: "
                    f"{id_resp.status} {id_resp.body}"
                )


def run_dry_run(base_url: str, env_path: Path) -> list[str]:
    """Print planned bootstrap steps without making network calls or writing files."""
    base = base_url.rstrip("/")
    steps = [
        f"[dry-run] 1. Wait for GET {base}/health -> 200",
        f"[dry-run] 2. Register/login admin user {ADMIN_EMAIL} at {base}/api/v1/auth/users/ & /api/v1/auth/login/",
        f"[dry-run] 3. Ensure organisation '{ORG_NAME}' via {base}/api/v1/organisations/",
        f"[dry-run] 4. Ensure project '{PROJECT_NAME}' via {base}/api/v1/projects/",
        f"[dry-run] 5. Fetch Development & Production environment keys via {base}/api/v1/environments/",
        f"[dry-run] 6. Create Admin API token via {base}/api/v1/organisations/<org_id>/master-api-keys/",
        f"[dry-run] 7. Write {env_path} with FLAGSMITH_API_URL, FLAGSMITH_SDK_API_URL, FLAGSMITH_API_KEY, FLAGSMITH_ENVIRONMENT, FLAGSMITH_ENV_KEY_PROD, FLAGSMITH_ENV_KEY_DEV",
        f"[dry-run] 8. Seed features {list(FEATURES)}, segments {[s['name'] for s in SEGMENTS]}, segment overrides, and {len(IDENTITIES)} identities",
    ]
    for line in steps:
        print(line)
    return steps


def bootstrap(
    *,
    base_url: str = "http://localhost:8000",
    env_path: Path = Path(".env"),
    password: str = DEFAULT_ADMIN_PASSWORD,
    timeout: float = 120.0,
    dry_run: bool = False,
    request_fn: RequestFn = default_http_request,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute the Flagsmith bootstrap workflow."""
    if dry_run:
        steps = run_dry_run(base_url, env_path)
        return {"dry_run": True, "steps": steps}

    wait_for_health(
        base_url, request_fn=request_fn, timeout=timeout, sleep_fn=sleep_fn
    )
    user_token = ensure_admin_token(
        base_url, password=password, request_fn=request_fn
    )
    auth_headers = {"Authorization": f"Token {user_token}"}

    org = ensure_organisation(base_url, auth_headers, request_fn=request_fn)
    org_id = int(org["id"])

    project = ensure_project(base_url, auth_headers, org_id, request_fn=request_fn)
    project_id = int(project["id"])

    envs = fetch_environments(
        base_url, auth_headers, project_id, request_fn=request_fn
    )
    prod_key = str(envs["Production"]["api_key"])
    dev_key = str(envs["Development"]["api_key"])

    admin_api_key = create_admin_api_token(
        base_url, auth_headers, org_id, user_token, request_fn=request_fn
    )

    write_env_file(
        env_path,
        api_url=base_url,
        api_key=admin_api_key,
        prod_env_key=prod_key,
        dev_env_key=dev_key,
    )

    seed_demo_data(
        base_url, auth_headers, project_id, envs, request_fn=request_fn
    )

    return {
        "dry_run": False,
        "org_id": org_id,
        "project_id": project_id,
        "env_file": str(env_path),
        "prod_env_key": prod_key,
        "dev_env_key": dev_key,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap self-hosted open-source Flagsmith for early-access demo."
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the self-hosted Flagsmith instance (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to write the generated .env file (default: .env)",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_ADMIN_PASSWORD,
        help="Admin user password (default: $FLAGSMITH_ADMIN_PASSWORD or EarlyAccessDemo123!)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Seconds to wait for Flagsmith /health (default: 120)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned steps without making HTTP calls or writing .env",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = bootstrap(
            base_url=args.url,
            env_path=Path(args.env_file),
            password=args.password,
            timeout=args.timeout,
            dry_run=args.dry_run,
        )
        if not result.get("dry_run"):
            print(
                f"Bootstrap complete: org_id={result['org_id']}, "
                f"project_id={result['project_id']}, env={result['env_file']}"
            )
        return 0
    except BootstrapError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
