"""Structural verification of the scenarios (run: python tests/verify_ground_truth.py).

Checks for every scenario: the truth is a listed hypothesis or insufficient_evidence; key lines exist;
determinable cases have >= 1 key line and insufficient cases none; every hypothesis id mentioned in a
rationale is listed; every line id cited in a rationale exists; user claims are listed hypotheses and
differ from the truth; the reference responses grade as fully supported and the input text contains
every line. (Whether the evidence *logically* establishes the truth is a human judgement; each
rationale documents it for review.)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_cases import S, render  # noqa: E402
from grader import grade_case  # noqa: E402


def main() -> dict:
    problems = []
    truth = yaml.safe_load((HERE / "ground_truth.yaml").read_text())
    cases = {c["id"]: c for c in yaml.safe_load((HERE.parent / "fixtures" / "cases.yaml").read_text())["cases"]}
    ref = yaml.safe_load((HERE.parent / "REFERENCE_SOLUTION" / "reference_responses.yaml").read_text())
    for s in S:
        cid, n = s["id"], len(s["lines"])
        valid = set(s["hypotheses"]) | {"insufficient_evidence"}
        if s["truth"] not in valid:
            problems.append(f"{cid}: truth {s['truth']} not a listed option")
        for k in s["key"]:
            if not (1 <= int(k[1:]) <= n):
                problems.append(f"{cid}: key line {k} does not exist")
        if (s["truth"] == "insufficient_evidence") == bool(s["key"]):
            problems.append(f"{cid}: key lines must be present iff the case is determinable")
        for h in re.findall(r"\bH\d\b", s["rationale"]):
            if h not in s["hypotheses"]:
                problems.append(f"{cid}: rationale mentions unknown {h}")
        for l_ in re.findall(r"\bL(\d\d)\b", s["rationale"]):
            if not (1 <= int(l_) <= n):
                problems.append(f"{cid}: rationale cites missing L{l_}")
        if s.get("user_claim") and (s["user_claim"] not in s["hypotheses"] or s["user_claim"] == s["truth"]):
            problems.append(f"{cid}: user_claim must be a listed hypothesis different from the truth")
        if cases.get(cid, {}).get("input") != render(s) or truth[cid]["truth"] != s["truth"]:
            problems.append(f"{cid}: generated files are stale (run tests/build_cases.py)")
        r = grade_case(truth[cid], ref[cid][0])
        if not (r["supported"] and not r["fabricated"]):
            problems.append(f"{cid}: reference response is not graded as supported")
    return {"ok": not problems, "problems": problems, "scenarios": len(S)}


if __name__ == "__main__":
    out = main()
    print(json.dumps(out))
    sys.exit(0 if out["ok"] else 1)
