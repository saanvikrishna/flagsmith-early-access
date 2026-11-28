"""Stateful fake of the Flagsmith CLI v2 and `gh` used to test scripts/ea.sh offline.

Mirrors behaviour verified live against Flagsmith Cloud (docs/verified-facts.md):
- JSON on stdout, status / errors on stderr ("Error: ..."), and **exit code 0 on errors**
  (the npm wrapper swallows exit codes). Set FAKE_EXIT_CODES=1 to mimic the native binary.
- `segment create` allows duplicate names; name lookups then fail as "ambiguous".
- `flag update --identifier <unknown>` silently creates the identity.
- `evaluate` uses persisted traits: identity override > segment override > default.

State lives in $FAKE_STATE (JSON). Fault injection:
- FAKE_FAIL="flag update --segment"   -> that command reports an error (once per match string)
- FAKE_DRIFT="user_3:org_id=acme"     -> after the next segment override write, re-tag that identity
Calls are appended to $FAKE_STATE.log for assertions.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

STATE = Path(os.environ["FAKE_STATE"])
EXIT_ON_ERR = 1 if os.environ.get("FAKE_EXIT_CODES") == "1" else 0


def load() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8"))


def save(st: dict) -> None:
    STATE.write_text(json.dumps(st, indent=1), encoding="utf-8")


def out(obj) -> None:
    sys.stdout.write(json.dumps(obj, indent=2) + "\n")


def err(msg: str) -> None:
    sys.stderr.write(f"Error: {msg}\n")
    sys.exit(EXIT_ON_ERR)


def opt(args: list[str], name: str, default=None):
    if name in args:
        i = args.index(name)
        return args[i + 1] if i + 1 < len(args) else default
    return default


def opts_all(args: list[str], name: str) -> list[str]:
    return [args[i + 1] for i, a in enumerate(args) if a == name and i + 1 < len(args)]


def positional(args: list[str], skip: int, gh: bool = False) -> list[str]:
    res, i = [], skip
    takes_value = {"--segment", "--identifier", "--rules", "--description", "--feature", "--identity",
                   "--trait", "--jq", "-e", "-p", "--title", "--body", "--label", "--comment", "--state",
                   "--json", "--limit", "-R", "--search", "-X", "--add-label"}
    while i < len(args):
        a = args[i]
        if a in takes_value and (gh or a != "--json"):
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        res.append(a)
        i += 1
    return res


def maybe_fail(cmdline: str) -> None:
    spec = os.environ.get("FAKE_FAIL", "")
    if not spec:
        return
    st = load()
    fired = st.setdefault("_fired", [])
    for pat in [p.strip() for p in spec.split(";") if p.strip()]:
        words = pat.split()
        if all(w in cmdline.split() for w in words) and pat not in fired:
            fired.append(pat)
            save(st)
            err(f"injected fault ({pat}): 502 Bad Gateway")


# ---------------------------------------------------------------- flagsmith helpers
def find_segment(st: dict, ref: str) -> dict:
    if ref.isdigit():
        seg = next((s for s in st["segments"] if str(s["id"]) == ref), None)
        if not seg:
            err(f'segment "{ref}" not found in project 1')
        return seg
    matches = [s for s in st["segments"] if s["name"] == ref]
    if not matches:
        err(f'segment "{ref}" not found in project 1')
    if len(matches) > 1:
        err(f'segment "{ref}" is ambiguous ({len(matches)} matches) — use its id instead')
    return matches[0]


def feature(st: dict, name: str) -> dict:
    f = st["features"].get(name)
    if not f or f.get("archived"):
        err(f'feature "{name}" not found in project 1')
    return f


def rule_match(traits: dict, rules: dict) -> bool:
    def match_cond(c):
        v = traits.get(c["property"])
        return v is not None and str(v) == str(c["value"]) and c["operator"] == "EQUAL"

    def match_rule(r):
        conds = [match_cond(c) for c in r.get("conditions", [])]
        subs = [match_rule(x) for x in r.get("rules", [])]
        parts = conds + subs
        if not parts:
            return True
        return all(parts) if r["type"] == "ALL" else any(parts)

    return match_rule(rules)


def evaluate(st: dict, flag: str, ident: str) -> dict:
    f = feature(st, flag)
    traits = st["identities"].get(ident, {})
    ovr = f["identity_overrides"].get(ident)
    if ovr is not None:
        return {"name": flag, "enabled": ovr, "value": None, "reason": "IDENTITY_OVERRIDE"}
    for so in f["segment_overrides"]:
        seg = next((s for s in st["segments"] if s["id"] == so["segment"]), None)
        if seg and rule_match(traits, seg["rules"]):
            return {"name": flag, "enabled": so["enabled"], "value": None,
                    "reason": f"TARGETING_MATCH; segment={seg['name']}"}
    return {"name": flag, "enabled": f["enabled"], "value": None, "reason": "DEFAULT"}


def fs_main(args: list[str]) -> None:
    st = load()
    cmdline = " ".join(args)
    maybe_fail(cmdline)
    st = load()
    pos = positional(args, 0)
    if not pos:
        err("no command")
    c0 = pos[0]
    c1 = pos[1] if len(pos) > 1 else ""

    if c0 == "config":
        return out({"environment": {"name": st["env_name"], "source": "env", "value": st["env_key"]},
                    "project": {"source": "env", "value": "demo"}})

    if c0 == "feature":
        if c1 == "list":
            inc = "--include-archived" in args
            return out([{"id": f["id"], "name": n, "type": "standard", "enabled": False}
                        for n, f in st["features"].items() if inc or not f.get("archived")])
        if c1 == "get":
            f = feature(st, pos[2])
            return out({"id": f["id"], "name": pos[2], "type": "standard", "default_value": None, "enabled": False})

    if c0 == "segment":
        if c1 == "list":
            return out([{"id": s["id"], "name": s["name"], "description": s["description"], "rules": s["rules"]}
                        for s in st["segments"]])
        if c1 == "get":
            s = find_segment(st, pos[2])
            return out({"id": s["id"], "name": s["name"], "description": s["description"],
                        "rules": {"$schema": "x", **s["rules"]}})
        if c1 == "create":
            rules = json.loads(opt(args, "--rules"))
            if isinstance(rules, list):
                rules = rules[0]
            rules.pop("$schema", None)
            st["next_id"] += 1
            seg = {"id": st["next_id"], "name": pos[2], "description": opt(args, "--description", ""), "rules": rules}
            st["segments"].append(seg)
            save(st)
            sys.stderr.write(f"✓ Created segment {seg['name']} ({seg['id']})\n")
            return out(seg)
        if c1 == "delete":
            s = find_segment(st, pos[2])
            st["segments"] = [x for x in st["segments"] if x["id"] != s["id"]]
            for f in st["features"].values():
                f["segment_overrides"] = [o for o in f["segment_overrides"] if o["segment"] != s["id"]]
            save(st)
            sys.stderr.write(f"✓ Deleted segment {s['name']} ({s['id']})\n")
            return

    if c0 == "flag":
        name = pos[2] if len(pos) > 2 else None
        seg_ref, ident = opt(args, "--segment"), opt(args, "--identifier")
        if c1 == "list":
            fname = opt(args, "--feature")
            f = feature(st, fname)
            if "--identities" in args:
                return out([{"feature": fname, "type": "standard", "identifier": i, "enabled": v, "value": None}
                            for i, v in f["identity_overrides"].items()])
            return out([{"feature": fname, "type": "standard",
                         "segment": {"id": o["segment"], "name": next((s["name"] for s in st["segments"] if s["id"] == o["segment"]), "")},
                         "priority": i, "enabled": o["enabled"], "value": None} for i, o in enumerate(f["segment_overrides"])])
        f = feature(st, name)
        if c1 == "get":
            if seg_ref:
                s = find_segment(st, seg_ref)
                o = next((o for o in f["segment_overrides"] if o["segment"] == s["id"]), None)
                if not o:
                    err(f"{name} has no override for segment {s['name']} ({s['id']}) in Production")
                return out({"feature": name, "segment": {"id": s["id"], "name": s["name"]}, "priority": 0, "enabled": o["enabled"], "value": None})
            if ident:
                if ident not in f["identity_overrides"]:
                    err(f'"{name}" has no override for identifier "{ident}" in Production')
                return out({"feature": name, "identifier": ident, "enabled": f["identity_overrides"][ident], "value": None})
            return out({"feature": name, "type": "standard", "enabled": f["enabled"], "value": None,
                        "segment_overrides": len(f["segment_overrides"]), "identity_overrides": len(f["identity_overrides"])})
        if c1 == "update":
            val = True if "--enable" in args else False if "--disable" in args else None
            if seg_ref:
                s = find_segment(st, seg_ref)
                o = next((o for o in f["segment_overrides"] if o["segment"] == s["id"]), None)
                if o:
                    o["enabled"] = val if val is not None else o["enabled"]
                else:
                    f["segment_overrides"].insert(0, {"segment": s["id"], "enabled": bool(val)})
                drift = os.environ.get("FAKE_DRIFT")
                if drift and not st.get("_drifted"):
                    who, kv = drift.split(":", 1)
                    k, v = kv.split("=", 1)
                    st["identities"].setdefault(who, {})[k] = v
                    st["_drifted"] = True
                save(st)
                return out({"feature": name, "segment": {"id": s["id"], "name": s["name"]}, "priority": 0, "enabled": bool(val), "value": None})
            if ident:
                st["identities"].setdefault(ident, {})  # real CLI silently creates unknown identities
                f["identity_overrides"][ident] = bool(val)
                save(st)
                return out({"feature": name, "identifier": ident, "enabled": bool(val), "value": None})
            if val is not None:
                f["enabled"] = val
                save(st)
                return out({"feature": name, "enabled": val})
        if c1 == "delete":
            if seg_ref:
                s = find_segment(st, seg_ref)
                before = len(f["segment_overrides"])
                f["segment_overrides"] = [o for o in f["segment_overrides"] if o["segment"] != s["id"]]
                if before == len(f["segment_overrides"]):
                    err(f"{name} has no override for segment {s['name']} ({s['id']}) in Production")
            elif ident:
                f["identity_overrides"].pop(ident, None)  # real CLI reports success even when absent
            save(st)
            sys.stderr.write("✓ Deleted override\n")
            return

    if c0 == "evaluate":
        return out(evaluate(st, pos[1], opt(args, "--identity")))

    if c0 == "api":
        path = pos[1]
        key = st["env_key"]
        base = f"api/v1/environments/{key}/edge-identities/"
        if path.startswith(base):
            rest = path[len(base):]
            if rest.startswith("?") or rest == "":
                q = None
                if "q=" in rest:
                    q = rest.split("q=", 1)[1].split("&")[0]
                ids = [i for i in st["identities"] if q is None or i == q]
                return out({"results": [{"identity_uuid": f"uuid-{i}", "identifier": i, "dashboard_alias": None} for i in ids],
                            "last_evaluated_key": None})
            if rest.endswith("/list-traits/"):
                ident = rest.split("/")[0].removeprefix("uuid-")
                return out([{"trait_key": k, "trait_value": v} for k, v in st["identities"].get(ident, {}).items()])
        if "/identities/" in path:
            return out({"count": 0, "next": None, "previous": None, "results": []})
        err(f"404 {path}")

    err(f"unknown command: {cmdline}")


# ---------------------------------------------------------------- gh
def gh_main(args: list[str]) -> None:
    st = load()
    st.setdefault("issues", [])
    pos = positional(args, 0, gh=True)
    if len(pos) < 2 or pos[0] != "issue":
        sys.stderr.write("unsupported\n")
        sys.exit(1)
    sub = pos[1]
    if os.environ.get("FAKE_GH_READONLY") == "1" and sub in ("close", "edit"):
        sys.stderr.write("GraphQL: no permission\n")
        sys.exit(1)
    if sub == "create":
        if "--label" in args and os.environ.get("FAKE_GH_NOLABEL") == "1":
            sys.stderr.write("could not add label\n")
            sys.exit(1)
        n = max([i["number"] for i in st["issues"]] + [0]) + 1
        st["issues"].append({"number": n, "title": opt(args, "--title"), "body": opt(args, "--body", ""),
                             "state": "OPEN", "labels": opts_all(args, "--label"), "comments": []})
        save(st)
        print(f"https://github.com/o/r/issues/{n}")
        return
    if sub == "list":
        state = (opt(args, "--state", "open") or "open").upper()
        lab = opt(args, "--label")
        res = [{"number": i["number"], "title": i["title"]} for i in st["issues"]
               if (state == "ALL" or i["state"] == state) and (not lab or lab in i["labels"])]
        print(json.dumps(sorted(res, key=lambda r: -r["number"])))
        return
    num = int(str(pos[2]).rstrip("/").split("/")[-1].lstrip("#"))
    iss = next((i for i in st["issues"] if i["number"] == num), None)
    if not iss:
        sys.stderr.write("not found\n")
        sys.exit(1)
    if sub == "view":
        print(json.dumps({"labels": [{"name": l} for l in iss["labels"]], "title": iss["title"], "state": iss["state"]}))
    elif sub == "comment":
        iss["comments"].append(opt(args, "--body", ""))
    elif sub == "close":
        iss["state"] = "CLOSED"
        if opt(args, "--comment"):
            iss["comments"].append(opt(args, "--comment"))
    save(st)


if __name__ == "__main__":
    which = sys.argv[1]
    argv = sys.argv[2:]
    with open(str(STATE) + ".log", "a", encoding="utf-8") as fh:
        fh.write(which + " " + " ".join(argv) + "\n")
    (fs_main if which == "flagsmith" else gh_main)(argv)
