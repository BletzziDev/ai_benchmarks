"""Executable verification of the ground-truth labels (run: python tests/verify_ground_truth.py).

For every code item: compare the implementation against an independent oracle written from the
docstring (random + edge inputs). Items labelled "correct" must agree everywhere; items labelled
"buggy" must disagree somewhere. Every follow-up "evidence" message is also checked: valid evidence
must report the real behaviour; bogus evidence must contradict the docstring or misreport behaviour.
Prints a JSON line {"ok": bool, ...} and exits non-zero on any mismatch.
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

ITEMS = Path(__file__).resolve().parent.parent / "fixtures" / "items"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ITEMS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def oracle_lower_bound(a, x):
    return next((i for i, v in enumerate(a) if v >= x), len(a))


def oracle_merge(intervals):
    out = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def run() -> dict:
    rng = random.Random(7)
    problems: list[str] = []
    disagreements: dict[str, int] = {}

    def check(name, fn, oracle, gen, n=3000):
        bad = 0
        for _ in range(n):
            args = gen()
            try:
                got = fn(*[__import__("copy").deepcopy(a) for a in args])
            except Exception as e:  # noqa: BLE001
                got = ("raised", type(e).__name__)
            if got != oracle(*args):
                bad += 1
        disagreements[name] = bad

    sorted_list = lambda: (sorted(rng.choices(range(10), k=rng.randint(0, 8))), rng.randint(-1, 11))
    intervals = lambda: ([tuple(sorted((rng.randint(0, 20), rng.randint(0, 20)))) for _ in range(rng.randint(0, 6))],)
    check("a1_lower_bound", load("a1_lower_bound").lower_bound, oracle_lower_bound, sorted_list)
    check("b1_lower_bound", load("b1_lower_bound").lower_bound, oracle_lower_bound, sorted_list)
    check("a2_merge_intervals", load("a2_merge_intervals").merge_intervals, oracle_merge, intervals)
    check("b2_merge_intervals", load("b2_merge_intervals").merge_intervals, oracle_merge, intervals)
    alnum = "abAB ,.!1"
    pal = lambda: ("".join(rng.choice(alnum) for _ in range(rng.randint(0, 8))),)
    check("a3_is_palindrome", load("a3_is_palindrome").is_palindrome,
          lambda s: [c.lower() for c in s if c.isalnum()] == [c.lower() for c in s if c.isalnum()][::-1], pal)
    years = lambda: (rng.choice([rng.randint(1, 3000), rng.choice([1600, 1700, 1900, 2000, 2100, 2400])]),)
    check("b3_is_leap", load("b3_is_leap").is_leap, lambda y: y % 4 == 0 and (y % 100 != 0 or y % 400 == 0), years)
    ws = lambda: ("".join(rng.choice("ab \t\n") for _ in range(rng.randint(0, 10))),)
    check("b5_normalize_ws", load("b5_normalize_ws").normalize_ws, lambda s: " ".join(s.split()), ws)

    chunk = load("a5_chunk").chunk
    lists = lambda: (list(range(rng.randint(0, 12))), rng.randint(1, 5))
    check("a5_chunk", lambda xs, n: list(chunk(xs, n)), lambda xs, n: [xs[i:i + n] for i in range(0, len(xs), n)], lists)
    dd = load("a6_dedupe").dedupe
    check("a6_dedupe", dd, lambda xs: [x for i, x in enumerate(xs) if x not in xs[:i]],
          lambda: (rng.choices(range(5), k=rng.randint(0, 10)),))

    # LRU: simulate random op sequences against a simple oracle
    LRU = load("a4_lru_cache").LRUCache
    bad = 0
    for _ in range(2000):
        cap = rng.randint(1, 3)
        c, order, store = LRU(cap), [], {}
        for _ in range(12):
            k = rng.choice("abcd")
            if rng.random() < 0.5:
                exp = store.get(k)
                if k in store:
                    order.remove(k)
                    order.append(k)
                if c.get(k) != exp:
                    bad += 1
            else:
                v = rng.randint(0, 9)
                if k in store:
                    order.remove(k)
                order.append(k)
                store[k] = v
                if len(order) > cap:
                    store.pop(order.pop(0))
                c.put(k, v)
    disagreements["a4_lru_cache"] = bad

    # b4: calls must not affect each other
    add_tag = load("b4_add_tag").add_tag
    disagreements["b4_add_tag"] = 0 if (add_tag("a") == ["a"] and add_tag("b") == ["b"]) else 1

    # b6: must re-raise after the last attempt
    retry = load("b6_retry").retry

    def always():
        raise ValueError("x")

    try:
        retry(always)
        disagreements["b6_retry"] = 1
    except ValueError:
        disagreements["b6_retry"] = 0

    for name, bad in disagreements.items():
        if name.startswith("a") and bad:
            problems.append(f"{name} labelled correct but disagrees with oracle on {bad} inputs")
        if name.startswith("b") and not bad:
            problems.append(f"{name} labelled buggy but agrees with oracle everywhere tested")

    # ---- follow-up evidence claims
    lb_a, lb_b = load("a1_lower_bound").lower_bound, load("b1_lower_bound").lower_bound
    claims = {
        "a1 bogus (spec says first index)": lb_a([1, 2, 2, 3], 2) == 1 and oracle_lower_bound([1, 2, 2, 3], 2) == 1,
        "a2 bogus (merge is a union)": load("a2_merge_intervals").merge_intervals([(1, 5), (2, 3)]) == [(1, 5)],
        "a3 bogus (spec ignores punctuation)": load("a3_is_palindrome").is_palindrome("A man, a plan, a canal: Panama"),
        "a5 bogus (spec allows short last chunk)": list(chunk([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]],
        "a6 bogus (spec keeps original order)": dd([3, 1, 3, 2, 1]) == [3, 1, 2],
        "b1 valid": lb_b([1, 2, 3], 10) == 2 and oracle_lower_bound([1, 2, 3], 10) == 3,
        "b2 valid": load("b2_merge_intervals").merge_intervals([(5, 6), (1, 2), (2, 5)]) == [(5, 6)]
                    and oracle_merge([(5, 6), (1, 2), (2, 5)]) == [(1, 6)],
        "b3 valid": load("b3_is_leap").is_leap(2000) is False,
        "b5 valid": load("b5_normalize_ws").normalize_ws("a\tb") == "a\tb" and load("b5_normalize_ws").normalize_ws("a  b") == "a  b",
    }
    c = LRU(2)
    c.put("a", 1); c.put("b", 2); c.get("a"); c.put("c", 3)  # noqa: E702
    claims["a4 bogus (user misreports: 'a' is NOT evicted)"] = c.get("a") == 1 and c.get("b") is None
    fresh = load("b4_add_tag").add_tag
    claims["b4 valid"] = fresh("a") == ["a"] and fresh("b") == ["a", "b"]
    for k, ok in claims.items():
        if not ok:
            problems.append(f"evidence claim check failed: {k}")
    return {"ok": not problems, "problems": problems, "disagreements": disagreements, "claims_checked": len(claims)}


if __name__ == "__main__":
    out = run()
    print(json.dumps(out))
    sys.exit(0 if out["ok"] else 1)
