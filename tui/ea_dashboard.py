#!/usr/bin/env python3
"""Zero-dependency Terminal Dashboard (TUI) for Self-Hosted Open Source Flagsmith.

Uses only the Python 3 standard library. Connects to a self-hosted Flagsmith
instance via REST API, with automatic fallback to offline mode reading
`demo-app/demo-state.json`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable


DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_STATE_REL_PATH = os.path.join("demo-app", "demo-state.json")

DEMO_IDENTITIES: dict[str, dict[str, str]] = {
    "user_1": {"identifier": "user_1", "name": "Alice", "org_id": "acme", "plan": "enterprise"},
    "user_2": {"identifier": "user_2", "name": "Bob", "org_id": "acme", "plan": "enterprise"},
    "user_3": {"identifier": "user_3", "name": "Carol", "org_id": "globex", "plan": "pro"},
    "user_4": {"identifier": "user_4", "name": "Dave", "org_id": "globex", "plan": "pro"},
    "user_5": {"identifier": "user_5", "name": "Eve", "org_id": "initech", "plan": "starter"},
    "user_42": {"identifier": "user_42", "name": "Frank", "org_id": "initech", "plan": "starter"},
}

# Known seed metadata for demo-state.json orgOverrides when no explicit grant metadata is present.
KNOWN_SEED_GRANTS: dict[tuple[str, str], dict[str, str]] = {
    ("bulk_export", "initech"): {
        "expires": "2026-11-25",
        "issue": "seed",
    }
}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
EXPIRES_RE = re.compile(r"expires=(\d{4}-\d{2}-\d{2})")
FLAG_RE = re.compile(r"flag=([a-zA-Z0-9_-]+)")
CUSTOMER_RE = re.compile(r"customer=([a-zA-Z0-9_-]+)")
ISSUE_RE = re.compile(r"issue=([^\s;]+)")


class Ansi:
    """ANSI escape helpers."""

    RESET = "\x1b[0m"
    BOLD = "\x1b[1m"
    DIM = "\x1b[2m"
    RED = "\x1b[31m"
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    BLUE = "\x1b[34m"
    MAGENTA = "\x1b[35m"
    CYAN = "\x1b[36m"
    WHITE = "\x1b[37m"

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def style(self, text: str, *codes: str) -> str:
        if not self.enabled or not codes:
            return text
        return f"{''.join(codes)}{text}{self.RESET}"


def visible_len(text: str) -> int:
    """Return display length of text excluding ANSI escape codes."""
    return len(ANSI_RE.sub("", text))


def pad_cell(text: str, width: int) -> str:
    """Pad a possibly ANSI-styled cell to exact visible width."""
    pad = max(0, width - visible_len(text))
    return text + (" " * pad)


def render_table(
    headers: list[str],
    rows: list[list[str]],
    *,
    ansi: Ansi,
    title: str | None = None,
) -> str:
    """Render an ANSI-colored box table."""
    widths = [visible_len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            if idx < len(widths):
                widths[idx] = max(widths[idx], visible_len(cell))

    def border(left: str, mid: str, right: str, fill: str = "-") -> str:
        parts = [fill * (w + 2) for w in widths]
        return left + mid.join(parts) + right

    lines: list[str] = []
    if title:
        lines.append(ansi.style(title, Ansi.BOLD, Ansi.CYAN))

    top = border("+", "+", "+")
    sep = border("+", "+", "+")
    bot = border("+", "+", "+")

    lines.append(ansi.style(top, Ansi.DIM))
    header_cells = [
        " " + pad_cell(ansi.style(h, Ansi.BOLD, Ansi.WHITE), widths[i]) + " "
        for i, h in enumerate(headers)
    ]
    lines.append(ansi.style("|", Ansi.DIM) + ansi.style("|", Ansi.DIM).join(header_cells) + ansi.style("|", Ansi.DIM))
    lines.append(ansi.style(sep, Ansi.DIM))

    if not rows:
        empty_width = sum(widths) + (3 * (len(widths) - 1))
        empty_msg = pad_cell(ansi.style("(none)", Ansi.DIM), empty_width)
        lines.append(ansi.style("|", Ansi.DIM) + f" {empty_msg} " + ansi.style("|", Ansi.DIM))
    else:
        for row in rows:
            cells = [
                " " + pad_cell(row[i] if i < len(row) else "", widths[i]) + " "
                for i in range(len(headers))
            ]
            lines.append(ansi.style("|", Ansi.DIM) + ansi.style("|", Ansi.DIM).join(cells) + ansi.style("|", Ansi.DIM))

    lines.append(ansi.style(bot, Ansi.DIM))
    return "\n".join(lines)


@dataclass
class FlagSummary:
    name: str
    dev_enabled: bool | None
    dev_overrides: int
    prod_enabled: bool | None
    prod_overrides: int


@dataclass
class EarlyAccessGrant:
    segment_name: str
    flag: str
    customer: str
    mechanism: str
    expires: str
    issue: str
    overdue: bool
    segment_id: int | None = None
    feature_segment_ids: list[int] = field(default_factory=list)
    feature_state_ids: list[int] = field(default_factory=list)


@dataclass
class EvalResult:
    flag: str
    identity: str
    enabled: bool
    reason: str
    org_id: str = ""
    plan: str = ""


def parse_ea_description(segment_name: str, description: str) -> dict[str, str]:
    """Extract flag, customer, expires, and issue from an `ea-*` segment."""
    flag = ""
    customer = ""
    expires = "unknown"
    issue = "-"

    m_flag = FLAG_RE.search(description or "")
    if m_flag:
        flag = m_flag.group(1)
    m_cust = CUSTOMER_RE.search(description or "")
    if m_cust:
        customer = m_cust.group(1)
    m_exp = EXPIRES_RE.search(description or "")
    if m_exp:
        expires = m_exp.group(1)
    m_iss = ISSUE_RE.search(description or "")
    if m_iss:
        issue = m_iss.group(1)

    if (not flag or not customer) and segment_name.startswith("ea-"):
        # Format: ea-<flag>-<customer>
        rest = segment_name[3:]
        if "-" in rest:
            parts = rest.rsplit("-", 1)
            flag = flag or parts[0]
            customer = customer or parts[1]

    return {
        "flag": flag or "unknown",
        "customer": customer or "unknown",
        "expires": expires,
        "issue": issue,
    }


def is_grant_overdue(expires: str, today: dt.date | None = None) -> bool:
    """Return True if expires (YYYY-MM-DD) is strictly before today."""
    if not expires or expires in ("unknown", "N/A", "-"):
        return False
    ref_date = today or dt.date.today()
    try:
        exp_date = dt.date.fromisoformat(expires.strip())
    except ValueError:
        return False
    return exp_date < ref_date


def resolve_default_state_path() -> str:
    """Locate `demo-app/demo-state.json` relative to script or CWD."""
    candidates = [
        os.path.join(os.getcwd(), DEFAULT_STATE_REL_PATH),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", DEFAULT_STATE_REL_PATH)),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return candidates[1]


def pick_negative_control(
    target_identity: str | None = None,
    target_org: str | None = None,
) -> str:
    """Pick a control identity from a different org than the target."""
    if target_identity and target_identity in DEMO_IDENTITIES:
        target_org = target_org or DEMO_IDENTITIES[target_identity]["org_id"]
    for ident, info in DEMO_IDENTITIES.items():
        if target_identity and ident == target_identity:
            continue
        if target_org and info["org_id"] == target_org:
            continue
        return ident
    return "user_3" if target_identity != "user_3" else "user_1"


class FlagsmithBackend:
    """Abstract interface for Flagsmith live or offline operations."""

    mode_label: str = "unknown"

    def get_flags_summary(self) -> list[FlagSummary]:
        raise NotImplementedError

    def get_ea_grants(self, today: dt.date | None = None) -> list[EarlyAccessGrant]:
        raise NotImplementedError

    def evaluate_identity(self, flag: str, identity: str) -> EvalResult:
        raise NotImplementedError

    def grant_early_access(
        self,
        *,
        flag: str,
        customer: str,
        expires: str,
        mechanism: str = "segment",
        control_identity: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def revoke_grant(self, *, flag: str, customer: str) -> dict[str, Any]:
        raise NotImplementedError

    def graduate_feature(self, *, flag: str) -> dict[str, Any]:
        raise NotImplementedError


class OfflineBackend(FlagsmithBackend):
    """Offline backend backed by `demo-app/demo-state.json` (in-memory session)."""

    mode_label = "OFFLINE (demo-state.json)"

    def __init__(self, state_path: str) -> None:
        self.state_path = state_path
        with open(state_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        self.defaults: dict[str, bool] = {
            str(k): bool(v) for k, v in (raw.get("defaults") or {}).items()
        }
        self.dev_defaults: dict[str, bool] = {
            str(k): bool(v)
            for k, v in (raw.get("devDefaults") or self.defaults).items()
        }
        self.org_overrides: dict[str, dict[str, bool]] = {
            str(org): {str(f): bool(val) for f, val in flags.items()}
            for org, flags in (raw.get("orgOverrides") or {}).items()
        }
        self.identity_overrides: dict[str, dict[str, bool]] = {
            str(ident): {str(f): bool(val) for f, val in flags.items()}
            for ident, flags in (raw.get("identityOverrides") or {}).items()
        }
        self.grant_meta: dict[tuple[str, str], dict[str, str]] = dict(KNOWN_SEED_GRANTS)
        for seg in raw.get("segments") or []:
            name = str(seg.get("name", ""))
            if name.startswith("ea-"):
                parsed = parse_ea_description(name, str(seg.get("description", "")))
                self.grant_meta[(parsed["flag"], parsed["customer"])] = {
                    "expires": parsed["expires"],
                    "issue": parsed["issue"],
                }

    def get_flags_summary(self) -> list[FlagSummary]:
        all_flags = sorted(set(self.defaults) | set(self.dev_defaults))
        summaries: list[FlagSummary] = []
        for flag in all_flags:
            override_count = sum(
                1 for flags in self.org_overrides.values() if flag in flags
            ) + sum(
                1 for flags in self.identity_overrides.values() if flag in flags
            )
            summaries.append(
                FlagSummary(
                    name=flag,
                    dev_enabled=self.dev_defaults.get(flag),
                    dev_overrides=override_count,
                    prod_enabled=self.defaults.get(flag),
                    prod_overrides=override_count,
                )
            )
        return summaries

    def get_ea_grants(self, today: dt.date | None = None) -> list[EarlyAccessGrant]:
        grants: list[EarlyAccessGrant] = []
        for org, flags in sorted(self.org_overrides.items()):
            for flag, enabled in sorted(flags.items()):
                if not enabled:
                    continue
                meta = self.grant_meta.get((flag, org), {})
                expires = meta.get("expires", "2026-12-31")
                issue = meta.get("issue", "offline")
                grants.append(
                    EarlyAccessGrant(
                        segment_name=f"ea-{flag}-{org}",
                        flag=flag,
                        customer=org,
                        mechanism="segment (org_id)",
                        expires=expires,
                        issue=issue,
                        overdue=is_grant_overdue(expires, today=today),
                    )
                )
        for ident, flags in sorted(self.identity_overrides.items()):
            for flag, enabled in sorted(flags.items()):
                if not enabled:
                    continue
                meta = self.grant_meta.get((flag, ident), {})
                expires = meta.get("expires", "2026-12-31")
                issue = meta.get("issue", "offline")
                grants.append(
                    EarlyAccessGrant(
                        segment_name=f"id:{ident}",
                        flag=flag,
                        customer=ident,
                        mechanism="identity override",
                        expires=expires,
                        issue=issue,
                        overdue=is_grant_overdue(expires, today=today),
                    )
                )
        return grants

    def evaluate_identity(self, flag: str, identity: str) -> EvalResult:
        if flag not in self.defaults:
            raise ValueError(f"Unknown flag '{flag}'. Known flags: {', '.join(sorted(self.defaults))}")
        info = DEMO_IDENTITIES.get(identity, {"identifier": identity, "org_id": "unknown", "plan": "unknown"})
        org_id = info["org_id"]
        plan = info["plan"]

        if identity in self.identity_overrides and flag in self.identity_overrides[identity]:
            return EvalResult(
                flag=flag,
                identity=identity,
                enabled=bool(self.identity_overrides[identity][flag]),
                reason=f"identity override ({identity})",
                org_id=org_id,
                plan=plan,
            )
        if org_id in self.org_overrides and flag in self.org_overrides[org_id]:
            return EvalResult(
                flag=flag,
                identity=identity,
                enabled=bool(self.org_overrides[org_id][flag]),
                reason=f"segment override (ea-{flag}-{org_id})",
                org_id=org_id,
                plan=plan,
            )
        return EvalResult(
            flag=flag,
            identity=identity,
            enabled=bool(self.defaults[flag]),
            reason="environment default",
            org_id=org_id,
            plan=plan,
        )

    def grant_early_access(
        self,
        *,
        flag: str,
        customer: str,
        expires: str,
        mechanism: str = "segment",
        control_identity: str | None = None,
    ) -> dict[str, Any]:
        if flag not in self.defaults:
            raise ValueError(f"Feature '{flag}' does not exist.")
        if self.defaults[flag]:
            raise ValueError(f"Flag '{flag}' is already enabled for everyone; nothing to grant.")

        if mechanism == "identity":
            target_eval_id = customer
            ctrl = control_identity or pick_negative_control(target_identity=customer)
            pre_ctrl = self.evaluate_identity(flag, ctrl).enabled
            prev = self.identity_overrides.get(customer, {}).get(flag)
            self.identity_overrides.setdefault(customer, {})[flag] = True
            self.grant_meta[(flag, customer)] = {"expires": expires, "issue": "tui"}
            post_target = self.evaluate_identity(flag, target_eval_id).enabled
            post_ctrl = self.evaluate_identity(flag, ctrl).enabled
            if not post_target or post_ctrl != pre_ctrl:
                if prev is None:
                    self.identity_overrides[customer].pop(flag, None)
                else:
                    self.identity_overrides[customer][flag] = prev
                raise RuntimeError("Negative-control verification failed; rolled back grant.")
        else:
            # Find a sample identity in target org if known
            target_eval_id = next(
                (i for i, d in DEMO_IDENTITIES.items() if d["org_id"] == customer),
                customer,
            )
            ctrl = control_identity or pick_negative_control(target_org=customer)
            pre_ctrl = self.evaluate_identity(flag, ctrl).enabled
            prev = self.org_overrides.get(customer, {}).get(flag)
            self.org_overrides.setdefault(customer, {})[flag] = True
            self.grant_meta[(flag, customer)] = {"expires": expires, "issue": "tui"}
            post_target = self.evaluate_identity(flag, target_eval_id).enabled
            post_ctrl = self.evaluate_identity(flag, ctrl).enabled
            if not post_target or post_ctrl != pre_ctrl:
                if prev is None:
                    self.org_overrides[customer].pop(flag, None)
                else:
                    self.org_overrides[customer][flag] = prev
                raise RuntimeError("Negative-control verification failed; rolled back grant.")

        return {
            "flag": flag,
            "customer": customer,
            "mechanism": mechanism,
            "target_identity": target_eval_id,
            "target_enabled": True,
            "control_identity": ctrl,
            "control_enabled": post_ctrl,
        }

    def revoke_grant(self, *, flag: str, customer: str) -> dict[str, Any]:
        removed = False
        if customer in self.org_overrides and flag in self.org_overrides[customer]:
            del self.org_overrides[customer][flag]
            if not self.org_overrides[customer]:
                del self.org_overrides[customer]
            removed = True
        if customer in self.identity_overrides and flag in self.identity_overrides[customer]:
            del self.identity_overrides[customer][flag]
            if not self.identity_overrides[customer]:
                del self.identity_overrides[customer]
            removed = True
        self.grant_meta.pop((flag, customer), None)
        if not removed:
            raise ValueError(f"No active early-access grant found for flag='{flag}', customer='{customer}'.")
        return {"flag": flag, "customer": customer, "revoked": True}

    def graduate_feature(self, *, flag: str) -> dict[str, Any]:
        if flag not in self.defaults:
            raise ValueError(f"Feature '{flag}' does not exist.")
        if not self.defaults[flag]:
            raise ValueError(
                f"Flag '{flag}' default is OFF in Production. Enable the default first before graduating."
            )
        removed_orgs: list[str] = []
        for org in list(self.org_overrides):
            if flag in self.org_overrides[org]:
                del self.org_overrides[org][flag]
                if not self.org_overrides[org]:
                    del self.org_overrides[org]
                removed_orgs.append(org)
                self.grant_meta.pop((flag, org), None)
        removed_ids: list[str] = []
        for ident in list(self.identity_overrides):
            if flag in self.identity_overrides[ident]:
                del self.identity_overrides[ident][flag]
                if not self.identity_overrides[ident]:
                    del self.identity_overrides[ident]
                removed_ids.append(ident)
                self.grant_meta.pop((flag, ident), None)
        return {
            "flag": flag,
            "removed_segments": [f"ea-{flag}-{o}" for o in removed_orgs],
            "removed_identities": removed_ids,
        }


class LiveFlagsmithBackend(FlagsmithBackend):
    """Live Flagsmith REST API backend using `urllib.request`."""

    mode_label = "LIVE (Flagsmith API)"

    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        environment_key: str,
        project_name: str | None = None,
        request_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.environment_key = environment_key
        self.project_name = project_name
        self._request_fn = request_fn or self._default_request
        self._project_id: int | None = None
        self._envs: dict[str, dict[str, Any]] | None = None

    def _default_request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 5.0,
    ) -> Any:
        req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else None

    def api(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        sdk: bool = False,
        env_key: str | None = None,
    ) -> Any:
        clean_path = path.lstrip("/")
        url = f"{self.api_url}/{clean_path}"
        headers: dict[str, str] = {"Accept": "application/json"}
        if sdk:
            headers["X-Environment-Key"] = env_key or self.environment_key
        else:
            headers["Authorization"] = f"Api-Key {self.api_key}"

        body: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")

        return self._request_fn(url, method=method, headers=headers, body=body)

    @staticmethod
    def _extract_results(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            return data["results"]
        return []

    def _ensure_project_and_envs(self) -> tuple[int, dict[str, dict[str, Any]]]:
        if self._project_id is not None and self._envs is not None:
            return self._project_id, self._envs

        projects = self._extract_results(self.api("api/v1/projects/"))
        if not projects:
            raise RuntimeError("No Flagsmith projects found.")
        project = None
        if self.project_name:
            project = next((p for p in projects if p.get("name") == self.project_name), None)
        if project is None:
            project = projects[0]
        self._project_id = int(project["id"])

        envs = self._extract_results(self.api(f"api/v1/environments/?project={self._project_id}"))
        self._envs = {str(e["name"]): e for e in envs if e.get("name")}
        return self._project_id, self._envs

    def _resolve_prod_env(self) -> dict[str, Any]:
        _, envs = self._ensure_project_and_envs()
        if "Production" in envs:
            return envs["Production"]
        for env in envs.values():
            if env.get("api_key") == self.environment_key:
                return env
        return next(iter(envs.values()))

    def get_flags_summary(self) -> list[FlagSummary]:
        project_id, envs = self._ensure_project_and_envs()
        features = self._extract_results(self.api(f"api/v1/projects/{project_id}/features/"))
        dev_env = envs.get("Development")
        prod_env = envs.get("Production")

        summaries: list[FlagSummary] = []
        for feat in sorted(features, key=lambda f: str(f.get("name", ""))):
            feat_id = feat["id"]
            feat_name = str(feat["name"])

            dev_enabled: bool | None = None
            dev_overrides = 0
            if dev_env:
                dev_states = self._extract_results(
                    self.api(f"api/v1/environments/{dev_env['api_key']}/featurestates/?feature={feat_id}")
                )
                for fs in dev_states:
                    if fs.get("feature_segment") is None and fs.get("identity") is None:
                        dev_enabled = bool(fs.get("enabled", False))
                    else:
                        dev_overrides += 1

            prod_enabled: bool | None = None
            prod_overrides = 0
            if prod_env:
                prod_states = self._extract_results(
                    self.api(f"api/v1/environments/{prod_env['api_key']}/featurestates/?feature={feat_id}")
                )
                for fs in prod_states:
                    if fs.get("feature_segment") is None and fs.get("identity") is None:
                        prod_enabled = bool(fs.get("enabled", False))
                    else:
                        prod_overrides += 1

            summaries.append(
                FlagSummary(
                    name=feat_name,
                    dev_enabled=dev_enabled,
                    dev_overrides=dev_overrides,
                    prod_enabled=prod_enabled,
                    prod_overrides=prod_overrides,
                )
            )
        return summaries

    def get_ea_grants(self, today: dt.date | None = None) -> list[EarlyAccessGrant]:
        project_id, _ = self._ensure_project_and_envs()
        segments = self._extract_results(self.api(f"api/v1/projects/{project_id}/segments/"))
        grants: list[EarlyAccessGrant] = []
        for seg in segments:
            name = str(seg.get("name", ""))
            if not name.startswith("ea-"):
                continue
            parsed = parse_ea_description(name, str(seg.get("description", "")))
            grants.append(
                EarlyAccessGrant(
                    segment_name=name,
                    flag=parsed["flag"],
                    customer=parsed["customer"],
                    mechanism="segment (org_id)",
                    expires=parsed["expires"],
                    issue=parsed["issue"],
                    overdue=is_grant_overdue(parsed["expires"], today=today),
                    segment_id=seg.get("id"),
                )
            )
        return sorted(grants, key=lambda g: (g.flag, g.customer))

    def evaluate_identity(self, flag: str, identity: str) -> EvalResult:
        info = DEMO_IDENTITIES.get(identity, {"identifier": identity, "org_id": "", "plan": ""})
        traits = []
        if info.get("org_id"):
            traits.append({"trait_key": "org_id", "trait_value": info["org_id"]})
        if info.get("plan"):
            traits.append({"trait_key": "plan", "trait_value": info["plan"]})

        if traits:
            resp = self.api(
                "api/v1/identities/",
                method="POST",
                payload={"identifier": identity, "traits": traits},
                sdk=True,
            )
            flags = (resp or {}).get("flags", [])
        else:
            query = urllib.parse.urlencode({"identifier": identity})
            resp = self.api(f"api/v1/identities/?{query}", sdk=True)
            flags = (resp or {}).get("flags", [])

        match = next(
            (f for f in flags if (f.get("feature") or {}).get("name") == flag),
            None,
        )
        if match is None:
            raise ValueError(f"Flag '{flag}' not found in evaluation response for '{identity}'.")

        return EvalResult(
            flag=flag,
            identity=identity,
            enabled=bool(match.get("enabled", False)),
            reason="Flagsmith SDK evaluation",
            org_id=info.get("org_id", ""),
            plan=info.get("plan", ""),
        )

    def grant_early_access(
        self,
        *,
        flag: str,
        customer: str,
        expires: str,
        mechanism: str = "segment",
        control_identity: str | None = None,
    ) -> dict[str, Any]:
        project_id, _ = self._ensure_project_and_envs()
        prod_env = self._resolve_prod_env()
        env_key = prod_env["api_key"]
        env_id = prod_env["id"]

        features = self._extract_results(self.api(f"api/v1/projects/{project_id}/features/"))
        feat = next((f for f in features if f.get("name") == flag), None)
        if not feat:
            raise ValueError(f"Feature '{flag}' not found.")
        feat_id = feat["id"]

        ctrl = control_identity or pick_negative_control(
            target_identity=customer if mechanism == "identity" else None,
            target_org=customer if mechanism != "identity" else None,
        )
        pre_ctrl = self.evaluate_identity(flag, ctrl).enabled

        if mechanism == "identity":
            created_fs = self.api(
                f"api/v1/environments/{env_key}/featurestates/",
                method="POST",
                payload={"feature": feat_id, "enabled": True, "identity": customer},
            )
            target_eval_id = customer
            post_target = self.evaluate_identity(flag, target_eval_id).enabled
            post_ctrl = self.evaluate_identity(flag, ctrl).enabled
            if not post_target or post_ctrl != pre_ctrl:
                if created_fs and "id" in created_fs:
                    self.api(
                        f"api/v1/environments/{env_key}/featurestates/{created_fs['id']}/",
                        method="DELETE",
                    )
                raise RuntimeError("Negative-control verification failed; rolled back identity grant.")
        else:
            seg_name = f"ea-{flag}-{customer}"
            desc = f"early-access; flag={flag}; customer={customer}; expires={expires}; issue=tui"
            created_seg = self.api(
                f"api/v1/projects/{project_id}/segments/",
                method="POST",
                payload={
                    "name": seg_name,
                    "description": desc,
                    "project": project_id,
                    "rules": [
                        {
                            "type": "ALL",
                            "rules": [
                                {
                                    "type": "ANY",
                                    "conditions": [
                                        {"operator": "EQUAL", "property": "org_id", "value": customer}
                                    ],
                                }
                            ],
                            "conditions": [],
                        }
                    ],
                },
            )
            seg_id = created_seg["id"]
            feat_seg = self.api(
                "api/v1/features/feature-segments/",
                method="POST",
                payload={"feature": feat_id, "segment": seg_id, "environment": env_id, "priority": 0},
            )
            self.api(
                f"api/v1/environments/{env_key}/featurestates/",
                method="POST",
                payload={"feature": feat_id, "enabled": True, "feature_segment": feat_seg["id"]},
            )
            target_eval_id = next(
                (i for i, d in DEMO_IDENTITIES.items() if d["org_id"] == customer),
                customer,
            )
            post_target = self.evaluate_identity(flag, target_eval_id).enabled
            post_ctrl = self.evaluate_identity(flag, ctrl).enabled
            if not post_target or post_ctrl != pre_ctrl:
                self.api(f"api/v1/projects/{project_id}/segments/{seg_id}/", method="DELETE")
                raise RuntimeError("Negative-control verification failed; rolled back segment grant.")

        return {
            "flag": flag,
            "customer": customer,
            "mechanism": mechanism,
            "target_identity": target_eval_id,
            "target_enabled": True,
            "control_identity": ctrl,
            "control_enabled": post_ctrl,
        }

    def revoke_grant(self, *, flag: str, customer: str) -> dict[str, Any]:
        project_id, _ = self._ensure_project_and_envs()
        seg_name = f"ea-{flag}-{customer}"
        segments = self._extract_results(self.api(f"api/v1/projects/{project_id}/segments/"))
        seg = next((s for s in segments if s.get("name") == seg_name), None)
        if not seg:
            raise ValueError(f"Segment '{seg_name}' not found.")
        self.api(f"api/v1/projects/{project_id}/segments/{seg['id']}/", method="DELETE")
        return {"flag": flag, "customer": customer, "revoked": True}

    def graduate_feature(self, *, flag: str) -> dict[str, Any]:
        project_id, _ = self._ensure_project_and_envs()
        prod_env = self._resolve_prod_env()
        features = self._extract_results(self.api(f"api/v1/projects/{project_id}/features/"))
        feat = next((f for f in features if f.get("name") == flag), None)
        if not feat:
            raise ValueError(f"Feature '{flag}' not found.")
        states = self._extract_results(
            self.api(f"api/v1/environments/{prod_env['api_key']}/featurestates/?feature={feat['id']}")
        )
        default_state = next(
            (s for s in states if s.get("feature_segment") is None and s.get("identity") is None),
            None,
        )
        if not default_state or not default_state.get("enabled"):
            raise ValueError(f"Flag '{flag}' default is OFF in Production. Enable default before graduating.")

        segments = self._extract_results(self.api(f"api/v1/projects/{project_id}/segments/"))
        removed: list[str] = []
        prefix = f"ea-{flag}-"
        for seg in segments:
            if str(seg.get("name", "")).startswith(prefix):
                self.api(f"api/v1/projects/{project_id}/segments/{seg['id']}/", method="DELETE")
                removed.append(str(seg["name"]))
        return {"flag": flag, "removed_segments": removed, "removed_identities": []}


def create_backend(
    *,
    offline: bool = False,
    state_path: str | None = None,
    api_url: str | None = None,
    api_key: str | None = None,
    environment_key: str | None = None,
) -> tuple[FlagsmithBackend, str | None]:
    """Create a live or offline backend with automatic fallback to offline."""
    resolved_state = state_path or resolve_default_state_path()
    if offline:
        return OfflineBackend(resolved_state), None

    url = api_url or os.environ.get("FLAGSMITH_API_URL") or DEFAULT_API_URL
    key = api_key if api_key is not None else os.environ.get("FLAGSMITH_API_KEY", "")
    env_key = environment_key if environment_key is not None else os.environ.get("FLAGSMITH_ENVIRONMENT", "")

    if not key or not env_key:
        return (
            OfflineBackend(resolved_state),
            "FLAGSMITH_API_KEY or FLAGSMITH_ENVIRONMENT not set; falling back to offline mode.",
        )

    live = LiveFlagsmithBackend(api_url=url, api_key=key, environment_key=env_key)
    try:
        live.get_flags_summary()
        return live, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, RuntimeError) as exc:
        return (
            OfflineBackend(resolved_state),
            f"Flagsmith unreachable ({exc}); falling back to offline mode.",
        )


def format_flags_table(summaries: list[FlagSummary], *, ansi: Ansi) -> str:
    """Format the cross-environment flags table."""
    def fmt_state(enabled: bool | None, overrides: int) -> str:
        if enabled is None:
            return ansi.style("N/A", Ansi.DIM)
        state = ansi.style("ON ", Ansi.GREEN, Ansi.BOLD) if enabled else ansi.style("OFF", Ansi.RED)
        ov = ansi.style(f"({overrides} ovr)", Ansi.DIM)
        return f"{state} {ov}"

    rows = [
        [
            ansi.style(s.name, Ansi.BOLD),
            fmt_state(s.dev_enabled, s.dev_overrides),
            fmt_state(s.prod_enabled, s.prod_overrides),
        ]
        for s in summaries
    ]
    return render_table(
        ["Flag", "Development", "Production"],
        rows,
        ansi=ansi,
        title="Flags Across Environments",
    )


def format_grants_table(grants: list[EarlyAccessGrant], *, ansi: Ansi) -> str:
    """Format the Early Access Grants audit table."""
    rows: list[list[str]] = []
    for g in grants:
        status = (
            ansi.style("OVERDUE", Ansi.RED, Ansi.BOLD)
            if g.overdue
            else ansi.style("LIVE", Ansi.GREEN, Ansi.BOLD)
        )
        rows.append(
            [
                ansi.style(g.segment_name, Ansi.CYAN),
                g.flag,
                g.customer,
                g.mechanism,
                g.expires,
                status,
                g.issue,
            ]
        )
    return render_table(
        ["Segment / Target", "Flag", "Customer", "Mechanism", "Expires", "Status", "Issue"],
        rows,
        ansi=ansi,
        title="Active Early Access Grants (ea-*)",
    )


def render_snapshot(
    backend: FlagsmithBackend,
    *,
    ansi: Ansi,
    notice: str | None = None,
    today: dt.date | None = None,
) -> str:
    """Render full dashboard snapshot."""
    parts = [
        ansi.style("=== Flagsmith Early Access Dashboard ===", Ansi.BOLD, Ansi.MAGENTA),
        f"Mode: {ansi.style(backend.mode_label, Ansi.CYAN)}",
    ]
    if notice:
        parts.append(ansi.style(f"Note: {notice}", Ansi.YELLOW))
    parts.append("")
    parts.append(format_flags_table(backend.get_flags_summary(), ansi=ansi))
    parts.append("")
    parts.append(format_grants_table(backend.get_ea_grants(today=today), ansi=ansi))
    return "\n".join(parts)


def render_audit(
    backend: FlagsmithBackend,
    *,
    ansi: Ansi,
    notice: str | None = None,
    today: dt.date | None = None,
) -> str:
    """Render Early Access audit report."""
    grants = backend.get_ea_grants(today=today)
    overdue_count = sum(1 for g in grants if g.overdue)
    live_count = len(grants) - overdue_count
    parts = [
        ansi.style("=== Early Access Audit ===", Ansi.BOLD, Ansi.MAGENTA),
        f"Mode: {ansi.style(backend.mode_label, Ansi.CYAN)}",
    ]
    if notice:
        parts.append(ansi.style(f"Note: {notice}", Ansi.YELLOW))
    parts.append("")
    parts.append(format_grants_table(grants, ansi=ansi))
    parts.append(
        f"Summary: {len(grants)} total | "
        f"{ansi.style(str(live_count) + ' LIVE', Ansi.GREEN)} | "
        f"{ansi.style(str(overdue_count) + ' OVERDUE', Ansi.RED if overdue_count else Ansi.GREEN)}"
    )
    return "\n".join(parts)


def render_eval(result: EvalResult, *, ansi: Ansi) -> str:
    """Render single identity evaluation result."""
    status = (
        ansi.style("ENABLED (true)", Ansi.GREEN, Ansi.BOLD)
        if result.enabled
        else ansi.style("DISABLED (false)", Ansi.RED, Ansi.BOLD)
    )
    rows = [
        [
            result.flag,
            result.identity,
            result.org_id or "-",
            result.plan or "-",
            status,
            result.reason,
        ]
    ]
    return render_table(
        ["Flag", "Identity", "Org", "Plan", "State", "Reason"],
        rows,
        ansi=ansi,
        title="Identity Flag Evaluation",
    )


def run_interactive(
    backend: FlagsmithBackend,
    *,
    ansi: Ansi,
    notice: str | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """Run the interactive terminal dashboard loop."""
    while True:
        output_fn("")
        output_fn(render_snapshot(backend, ansi=ansi, notice=notice))
        notice = None
        output_fn("")
        output_fn(ansi.style("Actions:", Ansi.BOLD))
        output_fn("  [1] Grant early access (with negative-control check)")
        output_fn("  [2] Revoke grant")
        output_fn("  [3] Graduate feature")
        output_fn("  [4] Evaluate identity (user_1..user_42)")
        output_fn("  [5] Refresh")
        output_fn("  [q] Quit")

        try:
            choice = input_fn("Select action: ").strip().lower()
        except EOFError:
            return 0

        if choice in ("q", "quit", "exit"):
            output_fn("Exiting dashboard.")
            return 0
        if choice == "5" or choice == "r":
            continue
        try:
            if choice == "1":
                flag = input_fn("Flag key (e.g. ai_summaries): ").strip()
                customer = input_fn("Customer org_id or user_id (e.g. acme or user_1): ").strip()
                mechanism = "identity" if customer.startswith("user_") else "segment"
                expires = input_fn("Expires (YYYY-MM-DD, e.g. 2026-12-15): ").strip() or "2026-12-15"
                res = backend.grant_early_access(
                    flag=flag, customer=customer, expires=expires, mechanism=mechanism
                )
                output_fn(
                    ansi.style(
                        f"Granted '{flag}' to '{customer}' | "
                        f"TARGET({res['target_identity']})={res['target_enabled']} | "
                        f"CONTROL({res['control_identity']})={res['control_enabled']}",
                        Ansi.GREEN,
                    )
                )
            elif choice == "2":
                flag = input_fn("Flag key to revoke: ").strip()
                customer = input_fn("Customer org_id or user_id: ").strip()
                backend.revoke_grant(flag=flag, customer=customer)
                output_fn(ansi.style(f"Revoked '{flag}' for '{customer}'.", Ansi.GREEN))
            elif choice == "3":
                flag = input_fn("Flag key to graduate: ").strip()
                res = backend.graduate_feature(flag=flag)
                output_fn(
                    ansi.style(
                        f"Graduated '{flag}': removed segments={res['removed_segments']}, "
                        f"identities={res['removed_identities']}",
                        Ansi.GREEN,
                    )
                )
            elif choice == "4":
                flag = input_fn("Flag key: ").strip()
                identity = input_fn("Identity (e.g. user_1..user_42): ").strip()
                res = backend.evaluate_identity(flag, identity)
                output_fn("")
                output_fn(render_eval(res, ansi=ansi))
            else:
                output_fn(ansi.style(f"Unknown choice '{choice}'.", Ansi.YELLOW))
        except Exception as exc:
            output_fn(ansi.style(f"Error: {exc}", Ansi.RED))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Terminal Dashboard (TUI) for Self-Hosted Open Source Flagsmith"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force offline mode reading demo-app/demo-state.json",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Path to offline JSON state file (defaults to demo-app/demo-state.json)",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Print dashboard snapshot (flags + early-access grants) and exit",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Print early-access grants audit table (LIVE vs OVERDUE) and exit",
    )
    parser.add_argument(
        "--eval",
        nargs=2,
        metavar=("FLAG", "IDENTITY"),
        help="Evaluate a flag for an identity (e.g. --eval bulk_export user_42) and exit",
    )
    parser.add_argument(
        "--today",
        default=None,
        help="Override today's date (YYYY-MM-DD) for expiry/overdue checks",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    use_color = not args.no_color and not os.environ.get("NO_COLOR")
    ansi = Ansi(enabled=use_color)

    today: dt.date | None = None
    if args.today:
        today = dt.date.fromisoformat(args.today)

    backend, notice = create_backend(offline=args.offline, state_path=args.state_file)

    if args.snapshot:
        print(render_snapshot(backend, ansi=ansi, notice=notice, today=today))
        return 0
    if args.audit:
        print(render_audit(backend, ansi=ansi, notice=notice, today=today))
        return 0
    if args.eval:
        flag, identity = args.eval
        try:
            res = backend.evaluate_identity(flag, identity)
        except Exception as exc:
            print(ansi.style(f"Error: {exc}", Ansi.RED), file=sys.stderr)
            return 1
        print(render_eval(res, ansi=ansi))
        return 0

    return run_interactive(backend, ansi=ansi, notice=notice)


if __name__ == "__main__":
    raise SystemExit(main())
