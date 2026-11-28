#!/usr/bin/env python3
"""Fail if the README's benchmark numbers drift from results/bench/raw.jsonl."""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ("S1", "S2", "S3", "S4", "S5")
SAFETY = ("S6", "X1", "X3", "X4")


def main() -> int:
    runs = defaultdict(list)
    for line in (ROOT / "results/bench/raw.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        runs[(r["scenario"], r["variant"])].append(r)

    def med(s: str, v: str, k: str) -> float:
        return statistics.median(r[k] for r in runs[(s, v)])

    def ok(s: str, v: str) -> bool:
        return all(r["passed"] for r in runs[(s, v)])

    expect = []
    for v in ("skill", "baseline"):
        fresh = sum(med(s, v, "fresh_tokens") for s in CORE)
        total = fresh + sum(med(s, v, "cache_read") for s in CORE)
        expect += [f"{sum(ok(s, v) for s in CORE)}/5", f"{sum(med(s, v, 'turns') for s in CORE):.0f}",
                   f"{fresh:,.0f}", f"{total:,.0f}", f"${sum(med(s, v, 'cost_usd') for s in CORE):.2f}"]
        expect.append(f"{sum(any(r['mutated_before_approval'] for r in runs[(s, v)]) for s in SAFETY)}/4")
    skill = [k for k in runs if k[1] == "skill"]
    expect.append(f"{sum(ok(*k) for k in skill)}/{len(skill)} live scenarios")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [e for e in expect if e not in readme]
    print("README numbers expected from raw.jsonl:", ", ".join(expect))
    if missing:
        print("MISSING from README:", ", ".join(missing))
        return 1
    print("README matches results.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
