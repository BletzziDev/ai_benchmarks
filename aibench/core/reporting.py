"""Aggregation, reports (JSON / Markdown / HTML) and model comparison.

Reports explain *why* a model scored what it did: per-criterion scores, critical failures, evidence
links, process metrics, usage and variability — not only a single number. Comparisons refuse to rank
runs whose conditions differ (benchmark hash, tier, tools, system kind, harness version) unless forced.
"""

from __future__ import annotations

import html
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from aibench.core.artifacts import RunStore, attempt_key
from aibench.core.config import Config
from aibench.core.registry import Registry
from aibench.core.stats import describe, paired_comparison, pass_at_k, pass_hat_k
from aibench.core.util import read_json, write_json


# --------------------------------------------------------------------------- aggregation


def collect_attempts(store: RunStore) -> list[dict[str, Any]]:
    out = []
    root = store.dir / "attempts"
    if not root.exists():
        return out
    for bdir in sorted(root.iterdir()):
        for adir in sorted(bdir.iterdir(), key=lambda p: int(p.name[1:]) if p.name[1:].isdigit() else 0):
            st = read_json(adir / "status.json") if (adir / "status.json").exists() else {}
            sc = read_json(adir / "score.json") if (adir / "score.json").exists() else None
            ev = read_json(adir / "evaluation.json") if (adir / "evaluation.json").exists() else None
            out.append({"key": bdir.name, "attempt": adir.name, "dir": str(adir.relative_to(store.dir)),
                        "status": st, "score": sc, "usage": (ev or {}).get("usage"), "episode": (ev or {}).get("episode"),
                        "check_status": {k: v["status"] for k, v in (ev or {}).get("checks", {}).items()}})
    return out


def summarize(store: RunStore, config: Config, registry: Registry | None = None) -> dict[str, Any]:
    m = store.manifest()
    attempts = collect_attempts(store)
    stats_cfg = config.scoring.stats
    by_bench: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for a in attempts:
        by_bench[a["key"]].append(a)
    benches = []
    cats: dict[str, list[float]] = defaultdict(list)
    for bmeta in m["benchmarks"]:
        key = attempt_key(bmeta["id"])
        atts = by_bench.get(key, [])
        done = [a for a in atts if a["status"].get("state") == "completed" and a["score"]]
        scores = [a["score"]["score"] for a in done if a["score"]["score"] is not None]
        verdicts = [a["score"]["passed"] for a in done]
        n_pass = sum(1 for v in verdicts if v is True)
        n_verdict = sum(1 for v in verdicts if v is not None)
        crit = [c["id"] for a in done for c in a["score"]["critical_failures"] if c.get("triggered")]
        infra = sum(1 for a in atts if a["status"].get("state") == "infra_error")
        skipped = sum(1 for a in atts if a["status"].get("state") == "skipped")
        statuses = [a["score"]["status"] for a in done]
        usage = [a["usage"] or {} for a in done]

        def tot(field: str) -> float | None:
            vals = [u.get(field) for u in usage]
            if not vals or any(v is None for v in vals):
                return None
            return float(sum(vals))

        criteria: dict[str, list[float]] = defaultdict(list)
        for a in done:
            for c in a["score"]["criteria"]:
                if c["value"] is not None:
                    criteria[c["id"]].append(c["value"])
        d = describe(scores, stats_cfg.confidence)
        entry = {
            "id": bmeta["id"], "category": bmeta["category"], "version": bmeta["version"],
            "content_hash": bmeta["content_hash"], "planned_attempts": bmeta["attempts"],
            "completed_attempts": len(done), "infra_errors": infra, "skipped": skipped,
            "score": d, "pass_count": n_pass, "verdicts": n_verdict,
            "pass_rate": (n_pass / n_verdict) if n_verdict else None,
            "pass_at_1": pass_at_k(n_verdict, n_pass, 1) if n_verdict else None,
            "pass_hat_k": pass_hat_k(n_verdict, n_pass, n_verdict) if n_verdict else None,
            "critical_failures": crit, "critical_rate": (sum(1 for a in done if any(c.get("triggered") for c in a["score"]["critical_failures"])) / len(done)) if done else None,
            "provisional": any(s in ("provisional", "incomplete") for s in statuses),
            "criteria": {k: statistics.fmean(v) for k, v in criteria.items()},
            "wall_time_s": tot("wall_time_s"), "model_time_s": tot("model_time_s"), "tool_time_s": tot("tool_time_s"),
            "input_tokens": tot("input_tokens"), "output_tokens": tot("output_tokens"), "cost_usd": tot("cost_usd"),
            "tool_calls": tot("tool_calls"), "tool_errors": tot("tool_errors"), "retries": tot("retries"),
            "terminations": sorted({(a.get("episode") or {}).get("termination") or "?" for a in done}),
            "attempt_dirs": [a["dir"] for a in atts],
        }
        benches.append(entry)
        if d["mean"] is not None:
            cats[bmeta["category"]].append(d["mean"])
    cat_summary = {c: {"mean": statistics.fmean(v), "n_benchmarks": len(v)} for c, v in sorted(cats.items())}
    weights = config.scoring.category_weights
    overall = None
    if config.scoring.overall_aggregation == "mean_of_categories" and cat_summary:
        ws = {c: weights.get(c, 1.0) for c in cat_summary}
        overall = sum(cat_summary[c]["mean"] * w for c, w in ws.items()) / sum(ws.values())
    elif benches:
        vals = [b["score"]["mean"] for b in benches if b["score"]["mean"] is not None]
        overall = statistics.fmean(vals) if vals else None
    total_planned = sum(b["planned_attempts"] for b in benches)
    total_done = sum(b["completed_attempts"] for b in benches)
    all_done = [a for a in attempts if a["status"].get("state") == "completed" and a["score"]]
    verd = [a["score"]["passed"] for a in all_done if a["score"]["passed"] is not None]
    return {
        "run_id": store.run_id, "model": m["model"], "system_kind": m.get("system_kind"), "tier": m.get("tier"),
        "harness_version": m.get("harness_version"), "sandbox": m.get("sandbox"), "state": m.get("state"),
        "created_at": m.get("created_at"), "finished_at": m.get("finished_at"),
        "overall_score": overall,
        "overall_note": "mean of category means (equal weights unless configs/scoring.yaml says otherwise); "
                        "interpret together with the per-category profile, pass/critical rates and provisional flags",
        "categories": cat_summary, "benchmarks": benches,
        "completion_rate": (total_done / total_planned) if total_planned else None,
        "pass_rate": (sum(1 for v in verd if v) / len(verd)) if verd else None,
        "critical_failure_rate": (sum(1 for a in all_done if any(c.get("triggered") for c in a["score"]["critical_failures"])) / len(all_done)) if all_done else None,
        "infra_error_count": sum(b["infra_errors"] for b in benches),
        "provisional_benchmarks": [b["id"] for b in benches if b["provisional"]],
        "usage_totals": {k: _sum_or_none([b[k] for b in benches]) for k in
                         ("wall_time_s", "model_time_s", "tool_time_s", "input_tokens", "output_tokens", "cost_usd", "tool_calls")},
    }


def _sum_or_none(vals: list[Any]) -> float | None:
    if not vals or any(v is None for v in vals):
        return None
    return float(sum(vals))


def write_summary(store: RunStore, config: Config, registry: Registry | None = None) -> dict[str, Any]:
    s = summarize(store, config, registry)
    write_json(store.dir / "summary.json", s)
    (store.dir / "report.md").write_text(markdown_report(s), encoding="utf-8")
    (store.dir / "report.html").write_text(html_report([s]), encoding="utf-8")
    return s


# --------------------------------------------------------------------------- rendering


def _f(v: Any, nd: int = 1, pct: bool = False) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        return f"{v * 100:.{nd}f}%" if pct else f"{v:.{nd}f}"
    return str(v)


def markdown_report(s: dict[str, Any]) -> str:
    m = s["model"]
    lines = [
        f"# Benchmark report — `{m['label']}`", "",
        f"- Run: `{s['run_id']}` · state: **{s['state']}** · harness {s['harness_version']} · sandbox: {s['sandbox'].get('backend')}"
        f" (network isolated: {s['sandbox'].get('network_isolated')}, unprivileged: {s['sandbox'].get('privileges_dropped')})",
        f"- System kind: **{s['system_kind']}** (adapter `{m.get('adapter')}`, model `{m.get('model')}`) · tier: {s.get('tier') or 'default'}",
        f"- Applied params: `{json.dumps(m.get('applied_params', {}))}` · dropped: `{json.dumps(m.get('dropped_params', {}))}`",
        "",
        "## Summary", "",
        f"| Overall score | Pass rate | Critical-failure rate | Completion rate | Infra errors |",
        f"|---|---|---|---|---|",
        f"| {_f(s['overall_score'])} | {_f(s['pass_rate'], pct=True)} | {_f(s['critical_failure_rate'], pct=True)} | "
        f"{_f(s['completion_rate'], pct=True)} | {s['infra_error_count']} |", "",
        f"> {s['overall_note']}.", "",
    ]
    if s["provisional_benchmarks"]:
        lines += [f"> **Provisional:** {', '.join(s['provisional_benchmarks'])} have criteria pending (e.g. rubric "
                  "grading without a judge). Their scores exclude those criteria.", ""]
    lines += ["## Competency profile (category means)", "", "| Category | Mean score | Benchmarks |", "|---|---|---|"]
    for c, v in s["categories"].items():
        lines.append(f"| {c} | {_f(v['mean'])} | {v['n_benchmarks']} |")
    lines += ["", "## Benchmarks", "",
              "| Benchmark | Score (mean ± std, n) | 95% CI | Pass | Critical | Wall s | Model s | Tool s | Tokens in/out | Cost USD |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for b in s["benchmarks"]:
        d = b["score"]
        sc = f"{_f(d['mean'])} ± {_f(d['std'])} (n={d['n']})" + (" ⚠ provisional" if b["provisional"] else "")
        ci = f"[{_f(d['ci_low'])}, {_f(d['ci_high'])}]" if d["ci_low"] is not None else "n/a"
        crit = ", ".join(sorted(set(b["critical_failures"]))) or "—"
        lines.append(f"| `{b['id']}` v{b['version']} | {sc} | {ci} | {b['pass_count']}/{b['verdicts']} | {crit} | "
                     f"{_f(b['wall_time_s'])} | {_f(b['model_time_s'])} | {_f(b['tool_time_s'])} | "
                     f"{_f(b['input_tokens'], 0)}/{_f(b['output_tokens'], 0)} | {_f(b['cost_usd'], 4)} |")
    lines += ["", "## Criteria detail", ""]
    for b in s["benchmarks"]:
        if not b["criteria"]:
            continue
        lines.append(f"**`{b['id']}`**: " + ", ".join(f"{k} {v * 100:.0f}%" for k, v in b["criteria"].items()))
        lines.append(f"  artifacts: {', '.join(f'`{d}`' for d in b['attempt_dirs'])}")
        lines.append("")
    tot = s["usage_totals"]
    lines += ["## Usage and cost", "",
              f"- Wall-clock: {_f(tot['wall_time_s'])} s (model {_f(tot['model_time_s'])} s, tools {_f(tot['tool_time_s'])} s). "
              "Budget tiers are limits, not elapsed time.",
              f"- Tokens: in {_f(tot['input_tokens'], 0)}, out {_f(tot['output_tokens'], 0)} "
              "(n/a = not reported by the provider; never estimated).",
              f"- Cost: {_f(tot['cost_usd'], 4)} USD (n/a when pricing is not declared in models.yaml or usage is missing).", ""]
    return "\n".join(lines)


def _bar(value: float | None, width: int = 160) -> str:
    if value is None:
        return '<span class="na">n/a</span>'
    w = max(0.0, min(100.0, value)) / 100 * width
    return (f'<svg width="{width}" height="12" role="img" aria-label="{value:.1f}"><rect width="{width}" height="12" '
            f'rx="3" class="track"/><rect width="{w:.1f}" height="12" rx="3" class="fill"/></svg> {value:.1f}')


def html_report(summaries: list[dict[str, Any]], comparison: dict[str, Any] | None = None) -> str:
    """Self-contained HTML (no external assets)."""
    e = html.escape
    title = "Benchmark report" if len(summaries) == 1 else "Model comparison"
    cats = sorted({c for s in summaries for c in s["categories"]})
    benches = sorted({b["id"] for s in summaries for b in s["benchmarks"]})
    head = "".join(f"<th>{e(s['model']['label'])}<br><small>{e(s['run_id'])}</small></th>" for s in summaries)
    rows_overall = "".join(f"<td>{_bar(s['overall_score'])}</td>" for s in summaries)
    rows_pass = "".join(f"<td>{_f(s['pass_rate'], pct=True)}</td>" for s in summaries)
    rows_crit = "".join(f"<td>{_f(s['critical_failure_rate'], pct=True)}</td>" for s in summaries)
    rows_kind = "".join(f"<td>{e(str(s['system_kind']))}</td>" for s in summaries)
    cat_rows = ""
    for c in cats:
        cells = "".join(f"<td>{_bar(s['categories'].get(c, {}).get('mean'))}</td>" for s in summaries)
        cat_rows += f"<tr><th scope='row'>{e(c)}</th>{cells}</tr>"
    bench_rows = ""
    for bid in benches:
        cells = ""
        for s in summaries:
            b = next((x for x in s["benchmarks"] if x["id"] == bid), None)
            if not b:
                cells += "<td class='na'>—</td>"
                continue
            d = b["score"]
            extra = f"<br><small>pass {b['pass_count']}/{b['verdicts']}"
            if b["critical_failures"]:
                extra += f" · <span class='crit'>critical: {e(', '.join(sorted(set(b['critical_failures']))))}</span>"
            if b["provisional"]:
                extra += " · provisional"
            if d["std"] is not None:
                extra += f" · ±{d['std']:.1f} (n={d['n']})"
            extra += "</small>"
            cells += f"<td>{_bar(d['mean'])}{extra}</td>"
        bench_rows += f"<tr><th scope='row'><code>{e(bid)}</code></th>{cells}</tr>"
    comp_html = ""
    if comparison:
        comp_html = "<h2>Paired comparison</h2>"
        if comparison.get("warnings"):
            comp_html += "<div class='warn'><strong>Comparability warnings</strong><ul>" + "".join(
                f"<li>{e(w)}</li>" for w in comparison["warnings"]) + "</ul></div>"
        for p in comparison.get("pairs", []):
            comp_html += (f"<p><strong>{e(p['a'])}</strong> vs <strong>{e(p['b'])}</strong>: mean difference "
                          f"{_f(p['mean_diff'])} points, 95% bootstrap CI [{_f(p['ci_low'])}, {_f(p['ci_high'])}] over "
                          f"{p['n_pairs']} benchmarks — {e(p['verdict'])}; wins/losses/ties {p['wins']}/{p['losses']}/{p['ties']}.</p>")
    css = """
:root{--bg:#ffffff;--fg:#1d2330;--muted:#5b6475;--line:#e3e6ec;--fill:#3a6ff7;--track:#e9edf5;--crit:#b42318;--warn-bg:#fff7e6}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#11141a;--fg:#e8ebf1;--muted:#9aa3b5;--line:#2a2f3a;--fill:#6f95ff;--track:#232937;--crit:#ff7a6e;--warn-bg:#2a2414}}
:root[data-theme="dark"]{--bg:#11141a;--fg:#e8ebf1;--muted:#9aa3b5;--line:#2a2f3a;--fill:#6f95ff;--track:#232937;--crit:#ff7a6e;--warn-bg:#2a2414}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:24px 16px;max-width:1200px;margin-inline:auto}
h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.15rem;margin:32px 0 8px}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;min-width:560px}th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
thead th{font-size:.85rem;color:var(--muted)}small,.na{color:var(--muted)}.crit{color:var(--crit)}
svg .track{fill:var(--track)}svg .fill{fill:var(--fill)}svg{vertical-align:middle}
.warn{background:var(--warn-bg);padding:8px 12px;border-radius:8px}code{font-size:.85em}p.note{color:var(--muted)}
"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><style>{css}</style></head><body>
<h1>{e(title)}</h1><p class="note">Scores are 0–100 per benchmark. Overall = mean of category means. Always read the profile,
pass and critical-failure rates together with the score. “provisional” means some criteria (e.g. rubric) were not graded.</p>
<h2>Overview</h2><div class="table-wrap"><table><thead><tr><th></th>{head}</tr></thead><tbody>
<tr><th scope="row">Overall</th>{rows_overall}</tr><tr><th scope="row">Pass rate</th>{rows_pass}</tr>
<tr><th scope="row">Critical-failure rate</th>{rows_crit}</tr><tr><th scope="row">System kind</th>{rows_kind}</tr></tbody></table></div>
<h2>Competency profile</h2><div class="table-wrap"><table><thead><tr><th>Category</th>{head}</tr></thead><tbody>{cat_rows}</tbody></table></div>
<h2>Benchmarks</h2><div class="table-wrap"><table><thead><tr><th>Benchmark</th>{head}</tr></thead><tbody>{bench_rows}</tbody></table></div>
{comp_html}
</body></html>"""


# --------------------------------------------------------------------------- comparison


def _conditions(store: RunStore) -> dict[str, Any]:
    m = store.manifest()
    return {
        "system_kind": m.get("system_kind"), "tier": m.get("tier"), "harness_version": m.get("harness_version"),
        "benchmarks": {b["id"]: {"benchmark_hash": b["content_hash"], "tools": tuple(b.get("tools") or [])} for b in m["benchmarks"]},
        "sandbox": (m.get("sandbox") or {}).get("backend"),
    }


def compare_runs(stores: list[RunStore], config: Config, force: bool = False) -> dict[str, Any]:
    summaries = [summarize(s, config) for s in stores]
    conds = [_conditions(s) for s in stores]
    warnings: list[str] = []
    fields = set(config.scoring.comparability_fields)
    base = conds[0]
    for s, c in zip(summaries[1:], conds[1:]):
        for f in ("system_kind", "tier", "harness_version"):
            if f in fields and c[f] != base[f]:
                warnings.append(f"{s['run_id']}: {f} differs ({c[f]!r} vs {base[f]!r})")
        for bid in set(base["benchmarks"]) & set(c["benchmarks"]):
            for f in ("benchmark_hash", "tools"):
                if f in fields and c["benchmarks"][bid][f] != base["benchmarks"][bid][f]:
                    warnings.append(f"{bid}: {f} differs between runs")
    pairs = []
    stats_cfg = config.scoring.stats
    for i in range(len(summaries)):
        for j in range(i + 1, len(summaries)):
            a = {b["id"]: b["score"]["mean"] for b in summaries[i]["benchmarks"] if b["score"]["mean"] is not None}
            b = {b["id"]: b["score"]["mean"] for b in summaries[j]["benchmarks"] if b["score"]["mean"] is not None}
            pc = paired_comparison(a, b, stats_cfg.bootstrap_iterations, stats_cfg.confidence, stats_cfg.seed)
            pc.update({"a": summaries[i]["model"]["label"], "b": summaries[j]["model"]["label"]})
            pairs.append(pc)
    ranking = None
    if not warnings or force:
        ranking = sorted(((s["model"]["label"], s["overall_score"]) for s in summaries),
                         key=lambda x: -(x[1] if x[1] is not None else -1))
    return {"runs": [s["run_id"] for s in summaries], "warnings": warnings, "pairs": pairs, "ranking": ranking,
            "ranking_note": None if ranking else "ranking withheld: conditions differ (use --force to override)",
            "summaries": summaries}


def comparison_markdown(c: dict[str, Any]) -> str:
    lines = ["# Model comparison", ""]
    if c["warnings"]:
        lines += ["> **Comparability warnings** — differences in conditions can explain score differences:", ""]
        lines += [f"> - {w}" for w in c["warnings"]] + [""]
    summaries = c["summaries"]
    labels = [s["model"]["label"] for s in summaries]
    lines += ["| | " + " | ".join(f"`{l}`" for l in labels) + " |", "|---" * (len(labels) + 1) + "|"]
    lines.append("| Overall | " + " | ".join(_f(s["overall_score"]) for s in summaries) + " |")
    lines.append("| Pass rate | " + " | ".join(_f(s["pass_rate"], pct=True) for s in summaries) + " |")
    lines.append("| Critical rate | " + " | ".join(_f(s["critical_failure_rate"], pct=True) for s in summaries) + " |")
    lines.append("| Cost USD | " + " | ".join(_f(s["usage_totals"]["cost_usd"], 4) for s in summaries) + " |")
    cats = sorted({k for s in summaries for k in s["categories"]})
    for cat in cats:
        lines.append(f"| {cat} | " + " | ".join(_f(s["categories"].get(cat, {}).get("mean")) for s in summaries) + " |")
    lines.append("")
    for p in c["pairs"]:
        lines.append(f"- **{p['a']} − {p['b']}**: {_f(p['mean_diff'])} points (95% bootstrap CI "
                     f"[{_f(p['ci_low'])}, {_f(p['ci_high'])}], {p['n_pairs']} paired benchmarks) → {p['verdict']}")
    lines.append("")
    if c["ranking"]:
        lines += ["Ranking (overall score): " + " > ".join(f"{l} ({_f(v)})" for l, v in c["ranking"]), ""]
    else:
        lines += [f"_{c['ranking_note']}_", ""]
    return "\n".join(lines)
