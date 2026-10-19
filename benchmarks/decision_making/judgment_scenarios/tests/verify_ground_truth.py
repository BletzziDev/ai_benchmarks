"""Structural verification of the decision scenarios (run: python tests/verify_ground_truth.py).

For each scenario: options A-D all scored in [0, 1] with a rationale; exactly one best option
(score 1.0) so "best choice" is well defined; harmful options score 0; at least two options carry
partial or full credit or the scenario has a single defensible action (documented); the judgement
fields' answers are derivable from the text (the action is named in the input, and when
requires_authorization is true the policies mention approval/confirmation/sign-off); generated files
are up to date; the reference responses grade perfectly.
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

AUTH_WORDS = re.compile(r"approv|confirm|sign-off|requires? .*authori", re.IGNORECASE)


def main() -> dict:
    problems = []
    truth = yaml.safe_load((HERE / "ground_truth.yaml").read_text())
    cases = {c["id"]: c for c in yaml.safe_load((HERE.parent / "fixtures" / "cases.yaml").read_text())["cases"]}
    ref = yaml.safe_load((HERE.parent / "REFERENCE_SOLUTION" / "reference_responses.yaml").read_text())
    stats = {"auth_true": 0, "irreversible": 0}
    for s in S:
        cid = s["id"]
        if sorted(s["options"]) != ["A", "B", "C", "D"] or sorted(s["scores"]) != ["A", "B", "C", "D"]:
            problems.append(f"{cid}: options/scores must cover A-D")
        if sorted(s["rationale"]) != ["A", "B", "C", "D"]:
            problems.append(f"{cid}: every option needs a rationale")
        if sum(v == 1.0 for v in s["scores"].values()) != 1:
            problems.append(f"{cid}: exactly one best option required")
        for h in s["harmful"]:
            if s["scores"][h] != 0.0:
                problems.append(f"{cid}: harmful option {h} must score 0")
        if s["truth"]["requires_authorization"] and not AUTH_WORDS.search(s["policies"]):
            problems.append(f"{cid}: authorization required but policies do not mention approval")
        stats["auth_true"] += s["truth"]["requires_authorization"]
        stats["irreversible"] += not s["truth"]["reversible"]
        if cases.get(cid, {}).get("input") != render(s):
            problems.append(f"{cid}: cases.yaml is stale (run tests/build_cases.py)")
        r = grade_case(truth[cid], ref[cid][0])
        if r["score"] != 1.0 or r["fields_correct"] != 2:
            problems.append(f"{cid}: reference response not perfect")
    n = len(S)
    best_pos = [max(s["scores"], key=s["scores"].get) for s in S]
    if max(best_pos.count(x) for x in "ABCD") > n / 4 + 1:
        problems.append(f"best options are not balanced across positions: {best_pos}")
    if not (0.25 * n <= stats["auth_true"] <= 0.75 * n) or not (0.2 * n <= stats["irreversible"] <= 0.8 * n):
        problems.append(f"judgement fields are unbalanced (a constant answer would score well): {stats}")
    return {"ok": not problems, "problems": problems, "scenarios": n, **stats}


if __name__ == "__main__":
    out = main()
    print(json.dumps(out))
    sys.exit(0 if out["ok"] else 1)
