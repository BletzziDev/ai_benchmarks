# AIBENCH-CANARY: 4c1e9b77-frontend-agent-platform-grader — grading code, never shown to evaluated models.
"""Grader for frontend_design/agent_platform_site.

Static checks run here; browser checks run in ``site_probe.py`` inside an unprivileged,
network-isolated LocalSandbox (always local: the browser lives on the host, not in the Docker image).
The probe gets no RLIMIT_AS (Chromium reserves very large virtual address ranges) but keeps the CPU,
file-size and process limits, the scrubbed environment, the dropped uid and the empty network namespace.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from aibench.core.checks.base import CheckResult
from aibench.core.sandbox import LocalSandbox
from aibench.core.spec import SandboxSpec
from aibench.core.util import copy_tree, iter_files

HERE = Path(__file__).resolve().parent
PALETTE_HEX = ["0b1020", "4a5568", "ffffff", "f3f5fa", "dce1ec", "3346e8", "19c3a0"]
FRAMEWORK_MARKERS = [r"React\.createElement|react-dom", r"\bjQuery v\d|jquery\.min\.js", r"Bootstrap v\d|bootstrap\.min\.(css|js)",
                     r"tailwindcss|\b--tw-", r"\bVue\.js v\d|vue\.global", r"\bangular\.module\b"]
SCORED = ["site_found", "site_loaded", "overflow_free_rate", "tap_target_rate", "structure_rate", "content_fidelity",
          "palette_compliance", "contrast_pass_rate", "heading_ok", "a11y_names_mean", "typography_score",
          "spacing_grid_rate", "mobile_nav_score", "desktop_nav_ok", "pricing_score", "faq_score", "form_score",
          "focus_visible_rate", "skip_link_ok", "reduced_motion_ok", "components_mean", "console_clean",
          "no_external_requests", "external_requests", "within_budget", "hygiene_score", "framework_detected"]


def _resolve_chromium() -> str | None:
    env = os.environ.get("AIBENCH_CHROMIUM")
    if env and Path(env).exists():
        return env
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            path = p.chromium.executable_path
        if path and Path(path).exists():
            return path
    except Exception:
        pass
    fallback = "/opt/pw-browsers/chromium"
    return fallback if Path(fallback).exists() else None


def _static(site: Path) -> tuple[dict, list[str]]:
    m: dict = {}
    ev: list[str] = []
    texts = {}
    for f in iter_files(site):
        if f.suffix.lower() in (".html", ".htm", ".css", ".js", ".mjs", ".svg", ".json"):
            try:
                texts[str(f.relative_to(site))] = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                pass
    blob = "\n".join(texts.values())
    fw = [pat for pat in FRAMEWORK_MARKERS if re.search(pat, blob, re.IGNORECASE)]
    m["framework_detected"] = 1 if fw else 0
    if fw:
        ev.append(f"framework/library markers found: {fw}")
    ext = re.findall(r"""(?:src|href)\s*=\s*["'](?:https?:)?//[^"']+""", blob, re.IGNORECASE)
    ext += re.findall(r"""url\(\s*["']?(?:https?:)?//[^)"']+""", blob, re.IGNORECASE)
    ext += re.findall(r"@import\s+(?:url\()?\s*[\"']?(?:https?:)?//[^;]+", blob, re.IGNORECASE)
    m["external_refs_static"] = len(ext)
    if ext:
        ev.append(f"external references in source: {ext[:6]}")
    var_defs = re.findall(r"--[\w-]+\s*:\s*#([0-9a-fA-F]{6})\b", blob)
    defined = {v.lower() for v in var_defs} & set(PALETTE_HEX)
    m["palette_vars_defined"] = len(defined)
    m["font_face_rules"] = len(re.findall(r"@font-face", blob, re.IGNORECASE))
    return m, ev


def grade(ctx, check) -> CheckResult:
    site = ctx.final_workspace / "site"
    res = CheckResult()
    if not (site / "index.html").is_file():
        res.metrics = {k: 0 for k in SCORED}
        res.metrics["no_external_requests"] = 1  # nothing loaded; the critical failure 'no_site' applies
        res.evidence.append("site/index.html not found: nothing to evaluate")
        return res
    try:
        import playwright  # noqa: F401
    except ImportError:
        return CheckResult(status="error", error="playwright is not installed (pip install 'aibench[frontend]')",
                           evidence=["grader prerequisite missing: playwright"])
    chromium = _resolve_chromium()
    if not chromium:
        return CheckResult(status="error", error="no Chromium executable found (set AIBENCH_CHROMIUM)",
                           evidence=["grader prerequisite missing: chromium"])
    static_m, static_ev = _static(site)
    spec = SandboxSpec(memory_mb=0, cpu_seconds=900, max_file_mb=256, max_processes=4096, max_workspace_mb=2048,
                       network=False)
    sb = LocalSandbox(spec, ctx.config.suite.sandbox, max_output_chars=200_000)
    try:
        copy_tree(site, sb.root / "site")
        shutil.copy2(HERE / "site_probe.py", sb.root / "probe.py")
        (sb.root / "out").mkdir()
        sb.start()
        r = sb.run(f"python probe.py site out {chromium}", timeout_s=check.timeout_s)
        (ctx.artifacts_dir / "probe.log").write_text((r.stdout + "\n--- stderr ---\n" + r.stderr)[-50000:])
        result_path = sb.root / "out" / "result.json"
        for png in sorted((sb.root / "out").glob("*.png")):
            shutil.copy2(png, ctx.artifacts_dir / png.name)
        if r.timed_out or not result_path.exists():
            res.metrics = {k: 0 for k in SCORED}
            res.metrics.update(static_m)
            res.metrics["site_found"] = 1
            res.metrics["no_external_requests"] = 1 if static_m["external_refs_static"] == 0 else 0
            res.evidence.append("the page hung or crashed the browser probe (timeout / no result)")
            return res
        data = json.loads(result_path.read_text())
    finally:
        sb.close()
    if data.get("status") != "ok":
        return CheckResult(status="error", error=f"browser probe failed: {data.get('error')}",
                           evidence=data.get("evidence", []), details={"traceback": data.get("traceback")})
    m = data["metrics"]
    m.update(static_m)
    m["site_found"] = 1
    m["console_clean"] = 1 if m.get("console_errors", 0) == 0 else 0
    m["no_external_requests"] = 1 if m.get("external_requests", 0) == 0 and static_m["external_refs_static"] == 0 else 0
    hygiene = [1 if static_m["palette_vars_defined"] >= 4 else 0, 1 if m.get("inline_handlers", 1) == 0 else 0,
               1 if m.get("inline_styles", 99) <= 5 else 0, 1 if static_m["font_face_rules"] == 0 else 0]
    m["hygiene_score"] = sum(hygiene) / len(hygiene)
    res.metrics = m
    res.evidence = static_ev + data.get("evidence", [])
    res.evidence.append(f"probe took {data.get('duration_s')} s; {m.get('requests')} requests, {m.get('total_kb')} KB; "
                        f"screenshots: {[p.name for p in sorted(ctx.artifacts_dir.glob('*.png'))]}")
    return res
