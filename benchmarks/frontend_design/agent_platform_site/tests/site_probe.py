# AIBENCH-CANARY: 4c1e9b77-frontend-agent-platform-probe — grading code, never shown to evaluated models.
"""Headless-browser probe for frontend_design/agent_platform_site.

Runs inside an unprivileged, network-isolated sandbox:

    python site_probe.py <site_dir> <out_dir> <chromium_executable>

Every request is intercepted: files are served from <site_dir> under a fake origin; anything else
is aborted and recorded as an external request. Writes <out_dir>/result.json and screenshots.
The page's JavaScript is untrusted; the probe never evaluates strings coming from the page.
"""

from __future__ import annotations

import json
import mimetypes
import re
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright

ORIGIN = "http://orbital.test"
WIDTHS = [375, 768, 1280, 1920]
HEIGHTS = {375: 812, 768: 1024, 1280: 900, 1920: 1080}

PALETTE = {
    "ink": (11, 16, 32), "slate": (74, 85, 104), "paper": (255, 255, 255), "mist": (243, 245, 250),
    "line": (220, 225, 236), "orbit": (51, 70, 232), "mint": (25, 195, 160),
}
JUDGE_MAX_HEIGHT = 7800
PALETTE_TOLERANCE = 10.0  # Euclidean RGB distance (absorbs rounding)

REQUIRED_TEXT = [
    "Autonomous agents your operations team can trust", "Supervised autonomy for the enterprise",
    "Book a demo", "See how it works", "4.2M", "38%", "99.95%",
    "Guardrails by default", "Human-in-the-loop approvals", "Complete audit trail", "Connects to your stack",
    "Evaluated before production", "Enterprise-grade security",
    "Connect", "Design", "Validate", "Operate",
    "Northwind Logistics", "Helios Bank", "Fjord Retail Group", "Kestrel Health", "Atlas Energy", "Meridian Insurance",
    "Orbital cut our invoice exception backlog from nine days to under one",
    "The approval flows are what convinced our risk team",
    "Orbital was the only one that let us replay last quarter's tickets",
    "Starter", "Growth", "Enterprise", "Most popular", "$49", "$199", "Custom",
    "How long does a typical deployment take?", "Can agents take actions without approval?",
    "Where is our data stored?", "Which models do you use?", "What happens if an agent makes a mistake?",
    "Tell us about your team and we will tailor a 30-minute walkthrough to your workflows.",
    "Request demo", "© 2026 Orbital Agents, Inc. All rights reserved.",
]
SUCCESS_TEXT = "Thanks! Our team will contact you within one business day."
# Metrics that feed scoring default to 0 so that a page that fails to load scores 0 instead of
# making criteria "unavailable".
SCORED_DEFAULTS = ["site_loaded", "overflow_free_rate", "tap_target_rate", "structure_rate", "content_fidelity",
                   "palette_compliance", "contrast_pass_rate", "heading_ok", "a11y_names_mean", "typography_score",
                   "spacing_grid_rate", "mobile_nav_score", "desktop_nav_ok", "pricing_score", "faq_score",
                   "form_score", "focus_visible_rate", "skip_link_ok", "reduced_motion_ok"]


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


# --------------------------------------------------------------------------- colour helpers

_NUM = r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?"


def parse_color(s: str):
    """-> (r, g, b, a) in 0-255/0-1, or None if unparseable. Handles rgb/rgba/color(srgb ...)."""
    s = s.strip().lower()
    if s in ("transparent", ""):
        return (0, 0, 0, 0.0)
    m = re.match(rf"rgba?\(\s*({_NUM})[,\s]+({_NUM})[,\s]+({_NUM})(?:\s*[,/]\s*({_NUM})(%)?)?\s*\)", s)
    if m:
        a = float(m.group(4)) if m.group(4) else 1.0
        if m.group(5):
            a /= 100
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)), a)
    m = re.match(rf"color\(srgb\s+({_NUM})\s+({_NUM})\s+({_NUM})(?:\s*/\s*({_NUM})(%)?)?\s*\)", s)
    if m:
        a = float(m.group(4)) if m.group(4) else 1.0
        if m.group(5):
            a /= 100
        return (float(m.group(1)) * 255, float(m.group(2)) * 255, float(m.group(3)) * 255, a)
    return None


def palette_match(rgb):
    best, dist = None, 1e9
    for name, p in PALETTE.items():
        d = sum((a - b) ** 2 for a, b in zip(rgb, p)) ** 0.5
        if d < dist:
            best, dist = name, d
    return best, dist


def extract_colors(css_value: str):
    return re.findall(r"(rgba?\([^)]*\)|color\(srgb[^)]*\)|oklch\([^)]*\)|oklab\([^)]*\)|lab\([^)]*\)|lch\([^)]*\)|hsla?\([^)]*\))", css_value)


# --------------------------------------------------------------------------- in-page scripts (static strings)

AUDIT_JS = r"""
() => {
  const out = {colors: [], texts: [], headings: [], controls: [], names: [], imgs: [], spacing: [], fonts: [],
               paragraphs: [], h1: [], structure: {}, focusables: 0};
  const vis = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse') return false;
    let n = el;
    while (n && n.nodeType === 1) { if (getComputedStyle(n).display === 'none' || parseFloat(getComputedStyle(n).opacity) === 0) return false; n = n.parentElement; }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const tiny = (el) => { const r = el.getBoundingClientRect(); return r.width * r.height <= 4; };
  const ownText = (el) => Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
  const all = Array.from(document.querySelectorAll('body, body *')).filter(el => !['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','HEAD','META','LINK'].includes(el.tagName));
  const svgShapes = new Set(['path','circle','rect','ellipse','line','polyline','polygon','text','g','use','svg']);
  let idx = 0;
  for (const el of all) {
    idx++;
    if (!vis(el)) continue;
    const cs = getComputedStyle(el);
    const tag = el.tagName.toLowerCase();
    const txt = ownText(el);
    const isControl = ['input','select','textarea','button'].includes(tag);
    if (txt || isControl) out.colors.push({p: 'color', v: cs.color, t: tag});
    out.colors.push({p: 'background-color', v: cs.backgroundColor, t: tag});
    if (cs.backgroundImage && cs.backgroundImage !== 'none') out.colors.push({p: 'background-image', v: cs.backgroundImage, t: tag});
    for (const side of ['Top','Right','Bottom','Left']) {
      if (parseFloat(cs['border'+side+'Width']) > 0 && cs['border'+side+'Style'] !== 'none') out.colors.push({p: 'border-color', v: cs['border'+side+'Color'], t: tag});
    }
    if (cs.boxShadow && cs.boxShadow !== 'none') out.colors.push({p: 'box-shadow', v: cs.boxShadow, t: tag});
    if (svgShapes.has(tag) && el.namespaceURI === 'http://www.w3.org/2000/svg') {
      if (cs.fill && cs.fill !== 'none' && !cs.fill.startsWith('url')) out.colors.push({p: 'fill', v: cs.fill, t: tag});
      if (cs.stroke && cs.stroke !== 'none' && !cs.stroke.startsWith('url')) out.colors.push({p: 'stroke', v: cs.stroke, t: tag});
    }
    for (const pseudo of ['::before', '::after']) {
      const ps = getComputedStyle(el, pseudo);
      if (!ps.content || ps.content === 'none' || ps.content === 'normal' || ps.display === 'none') continue;
      out.colors.push({p: 'pseudo-background-color', v: ps.backgroundColor, t: tag + pseudo});
      if (ps.backgroundImage !== 'none') out.colors.push({p: 'pseudo-background-image', v: ps.backgroundImage, t: tag + pseudo});
      if (ps.content.replace(/["']/g, '').trim()) out.colors.push({p: 'pseudo-color', v: ps.color, t: tag + pseudo});
      for (const side of ['Top','Right','Bottom','Left']) {
        if (parseFloat(ps['border'+side+'Width']) > 0 && ps['border'+side+'Style'] !== 'none') out.colors.push({p: 'pseudo-border-color', v: ps['border'+side+'Color'], t: tag + pseudo});
      }
    }
    for (const prop of ['marginTop','marginRight','marginBottom','marginLeft','paddingTop','paddingRight','paddingBottom','paddingLeft','rowGap','columnGap']) {
      const v = parseFloat(cs[prop]);
      if (!isNaN(v) && v !== 0) out.spacing.push(Math.abs(v));
    }
    if (txt && el.namespaceURI !== 'http://www.w3.org/2000/svg') {
      out.fonts.push(cs.fontFamily);
      if (!tiny(el)) {
        // effective background + opacity
        let layers = [];
        let n = el, undetermined = false, opacity = 1;
        while (n && n.nodeType === 1) {
          const ns = getComputedStyle(n);
          opacity *= parseFloat(ns.opacity);
          if (ns.backgroundImage && ns.backgroundImage !== 'none') { undetermined = true; break; }
          layers.push(ns.backgroundColor);
          n = n.parentElement;
        }
        out.texts.push({fg: cs.color, layers, undetermined, opacity, size: parseFloat(cs.fontSize),
                        weight: parseInt(cs.fontWeight) || 400, text: txt.slice(0, 60), tag});
      }
    }
    if (tag === 'p' && txt) out.paragraphs.push({size: parseFloat(cs.fontSize), lh: cs.lineHeight});
  }
  out.headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).filter(h => getComputedStyle(h).display !== 'none').map(h => parseInt(h.tagName[1]));
  out.h1 = Array.from(document.querySelectorAll('h1')).map(h => parseFloat(getComputedStyle(h).fontSize));
  for (const c of document.querySelectorAll('input, select, textarea')) {
    if (['hidden','submit','button','reset','image'].includes((c.type || '').toLowerCase())) continue;
    const labels = c.labels ? Array.from(c.labels).filter(l => l.textContent.trim() && vis(l)) : [];
    out.controls.push({name: c.name || c.id, labelled: labels.length > 0});
  }
  for (const b of document.querySelectorAll('a[href], button, [role=button], [role=switch]')) {
    let name = (b.getAttribute('aria-label') || '').trim();
    if (!name && b.getAttribute('aria-labelledby')) name = b.getAttribute('aria-labelledby').split(/\s+/).map(i => (document.getElementById(i)||{}).textContent || '').join(' ').trim();
    if (!name) name = (b.textContent || '').trim();
    if (!name) name = Array.from(b.querySelectorAll('img[alt]')).map(i => i.alt).join(' ').trim();
    if (!name) name = (b.getAttribute('title') || '').trim();
    out.names.push(!!name);
  }
  out.imgs = Array.from(document.querySelectorAll('img')).map(i => i.hasAttribute('alt'));
  const q = (s) => document.querySelector(s);
  const qa = (s) => document.querySelectorAll(s);
  const header = q('header');
  const nav = header ? header.querySelector('nav[aria-label]') : null;
  const navHrefs = nav ? Array.from(nav.querySelectorAll('a')).map(a => a.getAttribute('href')) : [];
  const hero = q('section#hero');
  out.structure = {
    lang: !!(document.documentElement.getAttribute('lang') || '').trim(),
    header_nav: !!nav && ['#features','#how-it-works','#pricing','#faq','#contact'].every(h => navHrefs.includes(h)),
    nav_toggle: !!q('button#nav-toggle[aria-controls][aria-expanded]'),
    main: !!q('main#main'),
    skip_link: !!q('a[href="#main"]'),
    hero: !!hero && hero.querySelectorAll('h1').length === 1 && !!q('#hero-cta[href="#contact"]'),
    single_h1: qa('h1').length === 1,
    features: !!q('section#features') && qa('section#features h3').length >= 6,
    how_it_works: !!q('section#how-it-works ol') && qa('section#how-it-works ol > li').length >= 4,
    customers: !!q('section#customers') && qa('section#customers blockquote').length >= 3,
    pricing: !!q('section#pricing button#billing-toggle[role=switch]') && ['starter','growth','enterprise'].every(p => !!q(`section#pricing [data-plan="${p}"] [data-price]`)),
    faq: !!q('section#faq') && qa('section#faq button[aria-expanded][aria-controls]').length >= 5,
    contact: !!q('section#contact form#demo-form') && !!q('#form-status[role=status]'),
    form_fields: ['name','email','company','team_size','message','consent'].every(n => !!q(`form#demo-form [name="${n}"]`)),
    footer: !!q('footer'),
    section_order: (() => {
      const ids = ['hero','features','how-it-works','customers','pricing','faq','contact'];
      const els = ids.map(i => q('main section#' + i));
      if (els.some(e => !e)) return false;
      for (let i = 1; i < els.length; i++) if (!(els[i-1].compareDocumentPosition(els[i]) & Node.DOCUMENT_POSITION_FOLLOWING)) return false;
      return true;
    })(),
  };
  const clone = document.body.cloneNode(true);
  clone.querySelectorAll('script, style, template, noscript').forEach(n => n.remove());
  out.text = clone.textContent;
  out.inline_handlers = Array.from(document.querySelectorAll('*')).filter(el => Array.from(el.attributes).some(a => /^on[a-z]+$/.test(a.name))).length;
  out.inline_styles = document.querySelectorAll('[style]').length;
  return out;
}
"""

OVERFLOW_JS = "() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, bw: document.body ? document.body.scrollWidth : 0})"

TAP_JS = r"""
() => {
  const res = [];
  for (const el of document.querySelectorAll('a[href], button, input, select, textarea, [role=button], [role=switch], summary')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.width * r.height <= 4) continue; // visually hidden (e.g. unfocused skip link)
    if (el.tagName === 'A' && el.closest('p')) continue; // inline links in running text are exempt (WCAG 2.5.8)
    if (el.type === 'checkbox' || el.type === 'radio') { const l = el.labels && el.labels[0]; if (l) { const lr = l.getBoundingClientRect(); res.push(Math.max(r.height, lr.height) >= 24 && (r.width + lr.width) >= 24); continue; } }
    res.push(r.width >= 23.5 && r.height >= 23.5);
  }
  return res;
}
"""

FOCUS_STYLE_JS = r"""
(el) => { if (!el || el === document.body) return null; const cs = getComputedStyle(el);
  return {tag: el.tagName, outline: cs.outlineStyle + ' ' + cs.outlineWidth + ' ' + cs.outlineColor, os: cs.outlineStyle, ow: parseFloat(cs.outlineWidth),
          oc: cs.outlineColor, shadow: cs.boxShadow, border: cs.borderColor + cs.borderWidth, bg: cs.backgroundColor, deco: cs.textDecorationLine,
          rect: (() => { const r = el.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })(), href: el.getAttribute('href') || '' }; }
"""

MOTION_JS = r"""
() => {
  const anims = document.getAnimations ? document.getAnimations() : [];
  const running = anims.filter(a => a.playState === 'running').map(a => {
    const t = a.effect && a.effect.getComputedTiming ? a.effect.getComputedTiming() : {};
    return {duration: typeof t.duration === 'number' ? t.duration : 0, iterations: t.iterations === Infinity ? -1 : (t.iterations || 1)};
  });
  return {running, smooth: getComputedStyle(document.documentElement).scrollBehavior === 'smooth' || (document.body && getComputedStyle(document.body).scrollBehavior === 'smooth')};
}
"""


# --------------------------------------------------------------------------- probe


class Probe:
    def __init__(self, site: Path, out: Path, chromium: str):
        self.site = site.resolve()
        self.out = out
        self.chromium = chromium
        self.external: list[str] = []
        self.served: dict[str, int] = {}
        self.missing: list[str] = []
        self.non_get: list[str] = []
        self.font_requests = 0
        self.console_errors: list[str] = []
        self.m: dict = {}
        self.evidence: list[str] = []

    def handler(self, route):
        req = route.request
        url = req.url
        if not url.startswith(ORIGIN + "/"):
            self.external.append(url[:200])
            return route.abort()
        if req.method != "GET":
            self.non_get.append(f"{req.method} {url[:120]}")
            return route.fulfill(status=405, body="")
        path = unquote(urlparse(url).path).lstrip("/") or "index.html"
        target = (self.site / path).resolve()
        if target.is_dir():
            target = target / "index.html"
        if not target.is_relative_to(self.site) or not target.is_file():
            self.missing.append(path)
            return route.fulfill(status=404, body="not found")
        if req.resource_type == "font":
            self.font_requests += 1
        data = target.read_bytes()
        self.served[str(target.relative_to(self.site))] = len(data)
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return route.fulfill(status=200, body=data, headers={"content-type": ctype})

    def page(self, browser, width, reduced=False):
        ctx = browser.new_context(viewport={"width": width, "height": HEIGHTS.get(width, 900)}, device_scale_factor=1,
                                  reduced_motion="reduce" if reduced else "no-preference", service_workers="block")
        ctx.set_default_timeout(8000)
        ctx.route("**/*", self.handler)
        pg = ctx.new_page()
        pg.on("console", lambda msg: self.console_errors.append(msg.text[:300]) if msg.type == "error" else None)
        pg.on("pageerror", lambda exc: self.console_errors.append(f"uncaught: {str(exc)[:300]}"))
        pg.goto(ORIGIN + "/index.html", wait_until="load", timeout=15000)
        pg.wait_for_timeout(250)
        return ctx, pg

    @staticmethod
    def visible(pg, selector) -> bool:
        try:
            loc = pg.locator(selector).first
            return loc.count() > 0 and loc.is_visible()
        except Exception:
            return False

    def run(self) -> dict:
        m = self.m
        m.update({k: 0.0 for k in SCORED_DEFAULTS})
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=self.chromium, args=["--disable-gpu"])
            try:
                for name, fn in [("layout", self.layout_and_screenshots), ("audit", self.audit),
                                 ("mobile_nav", self.mobile_nav), ("desktop_nav", self.desktop_nav),
                                 ("pricing", self.pricing), ("faq", self.faq), ("form", self.form),
                                 ("keyboard", self.keyboard), ("motion", self.motion)]:
                    try:
                        fn(browser)
                    except Exception as e:  # a broken page must not break the probe
                        self.evidence.append(f"{name}: interaction failed: {type(e).__name__}: {str(e)[:200]}")
            finally:
                browser.close()
        m["external_requests"] = len(set(self.external))
        m["non_get_requests"] = len(self.non_get)
        m["missing_resources"] = len(set(self.missing))
        m["font_requests"] = self.font_requests
        m["console_errors"] = len(set(self.console_errors))
        total = sum(self.served.values())
        m["total_kb"] = round(total / 1024, 1)
        m["requests"] = len(self.served)
        m["within_budget"] = 1 if total <= 300 * 1024 and len(self.served) <= 20 else 0
        if self.external:
            self.evidence.append(f"external requests blocked: {sorted(set(self.external))[:8]}")
        if self.console_errors:
            self.evidence.append(f"console errors: {sorted(set(self.console_errors))[:6]}")
        if self.missing:
            self.evidence.append(f"missing local resources (404): {sorted(set(self.missing))[:8]}")
        comps = [m.get(k) for k in ("mobile_nav_score", "pricing_score", "faq_score", "form_score", "skip_link_ok")]
        m["components_mean"] = round(sum(c or 0 for c in comps) / len(comps), 4)
        return {"metrics": m, "evidence": self.evidence}

    # ------------------------------------------------------------------ layout
    def layout_and_screenshots(self, browser):
        ok = 0
        for w in WIDTHS:
            ctx, pg = self.page(browser, w)
            try:
                o = pg.evaluate(OVERFLOW_JS)
                over = max(o["sw"], o["bw"]) > o["cw"] + 1
                self.m[f"overflow_{w}"] = 1 if over else 0
                if over:
                    self.evidence.append(f"horizontal overflow at {w}px: scrollWidth={max(o['sw'], o['bw'])} > {o['cw']}")
                else:
                    ok += 1
                pg.screenshot(path=str(self.out / f"screenshot-{w:04d}.png"), full_page=True, timeout=20000)
                # Judge copy: vision APIs reject very tall images (e.g. > 8000 px), so clip the height.
                full_h = pg.evaluate("() => document.documentElement.scrollHeight")
                pg.screenshot(path=str(self.out / f"judge-{w:04d}.png"), full_page=True, timeout=20000,
                              clip={"x": 0, "y": 0, "width": w, "height": min(full_h, JUDGE_MAX_HEIGHT)})
                if w == 375:
                    taps = pg.evaluate(TAP_JS)
                    self.m["tap_target_rate"] = round(sum(taps) / len(taps), 4) if taps else 0.0
                    h1 = pg.evaluate("() => Array.from(document.querySelectorAll('h1')).map(h => parseFloat(getComputedStyle(h).fontSize))")
                    self.m["h1_mobile_px"] = max(h1) if h1 else 0
            finally:
                ctx.close()
        self.m["overflow_free_rate"] = ok / len(WIDTHS)

    # ------------------------------------------------------------------ static audit at 1280
    def audit(self, browser):
        ctx, pg = self.page(browser, 1280)
        try:
            a = pg.evaluate(AUDIT_JS)
        finally:
            ctx.close()
        m = self.m
        m["site_loaded"] = 1
        st = a["structure"]
        m["structure_rate"] = round(sum(1 for v in st.values() if v) / len(st), 4)
        missing = [k for k, v in st.items() if not v]
        if missing:
            self.evidence.append(f"structure requirements not met: {missing}")
        text = norm(a["text"])
        found = [t for t in REQUIRED_TEXT if norm(t) in text]
        m["content_fidelity"] = round(len(found) / len(REQUIRED_TEXT), 4)
        lost = [t for t in REQUIRED_TEXT if norm(t) not in text]
        if lost:
            self.evidence.append(f"required copy missing or altered: {lost[:8]}")
        # palette
        total = good = 0
        off: dict[str, int] = {}
        for c in a["colors"]:
            vals = extract_colors(c["v"]) if c["p"] in ("background-image", "pseudo-background-image", "box-shadow") else [c["v"]]
            for v in vals:
                col = parse_color(v)
                if col is not None and col[3] == 0:
                    continue  # fully transparent: no colour used
                total += 1
                if col is None:
                    off[f"{v} ({c['p']})"] = off.get(f"{v} ({c['p']})", 0) + 1
                    continue
                name, dist = palette_match(col[:3])
                if dist <= PALETTE_TOLERANCE:
                    good += 1
                else:
                    key = f"rgb({col[0]:.0f},{col[1]:.0f},{col[2]:.0f}) ({c['p']} on {c['t']})"
                    off[key] = off.get(key, 0) + 1
        m["palette_compliance"] = round(good / total, 4) if total else 0.0
        m["palette_samples"] = total
        if off:
            top = sorted(off.items(), key=lambda kv: -kv[1])[:8]
            self.evidence.append(f"off-palette colours (count): {top}")
        # contrast
        det = passed = 0
        undetermined = 0
        fails = []
        for t in a["texts"]:
            if t["undetermined"]:
                undetermined += 1
                continue
            fg = parse_color(t["fg"])
            if fg is None:
                undetermined += 1
                continue
            bg = (255.0, 255.0, 255.0)
            for layer in reversed(t["layers"]):
                c = parse_color(layer)
                if c is None or c[3] == 0:
                    continue
                bg = tuple(c[i] * c[3] + bg[i] * (1 - c[3]) for i in range(3))
            alpha = fg[3] * t["opacity"]
            fgc = tuple(fg[i] * alpha + bg[i] * (1 - alpha) for i in range(3))
            ratio = contrast(fgc, bg)
            large = t["size"] >= 24 or (t["size"] >= 18.66 and t["weight"] >= 700)
            det += 1
            if ratio >= (3.0 if large else 4.5) - 0.01:
                passed += 1
            else:
                fails.append(f"{t['tag']} '{t['text'][:30]}' {ratio:.2f}")
        m["contrast_pass_rate"] = round(passed / det, 4) if det else 0.0
        m["contrast_undetermined"] = undetermined
        if fails:
            self.evidence.append(f"contrast failures ({len(fails)}): {fails[:6]}")
        # headings
        hs = a["headings"]
        skips = sum(1 for i in range(1, len(hs)) if hs[i] > hs[i - 1] + 1)
        m["heading_ok"] = 1 if hs.count(1) == 1 and skips == 0 and hs and hs[0] == 1 else 0
        if not m["heading_ok"]:
            self.evidence.append(f"heading outline problem: levels={hs[:30]}")
        # labels / names / alt
        ctl = a["controls"]
        m["labels_rate"] = round(sum(c["labelled"] for c in ctl) / len(ctl), 4) if ctl else 0.0
        m["names_rate"] = round(sum(a["names"]) / len(a["names"]), 4) if a["names"] else 0.0
        m["img_alt_rate"] = round(sum(a["imgs"]) / len(a["imgs"]), 4) if a["imgs"] else 1.0
        m["a11y_names_mean"] = round((m["labels_rate"] + m["names_rate"] + m["img_alt_rate"]) / 3, 4)
        # typography
        fams = [f.split(",")[0].strip().strip('"').strip("'").lower() for f in a["fonts"]]
        allowed = {"system-ui", "-apple-system", "ui-monospace", "ui-sans-serif"}
        fam_ok = sum(1 for f in fams if f in allowed) / len(fams) if fams else 0.0
        h1 = max(a["h1"]) if a["h1"] else 0
        paras = a["paragraphs"]

        def lh_ok(p):
            try:
                return 1.4 <= float(p["lh"].replace("px", "")) / p["size"] <= 1.8
            except ValueError:
                return False
        para_ok = sum(1 for p in paras if p["size"] >= 16 and lh_ok(p)) / len(paras) if paras else 0.0
        h1_ok = (1 if h1 >= 40 else 0) * 0.5 + (1 if self.m.get("h1_mobile_px", 0) >= 30 else 0) * 0.5
        distinct = len(set(fams))
        m["typography_score"] = round((fam_ok + para_ok + h1_ok + (1 if distinct <= 2 and self.font_requests == 0 else 0)) / 4, 4)
        m["font_family_rate"] = round(fam_ok, 4)
        m["paragraph_type_rate"] = round(para_ok, 4)
        m["h1_desktop_px"] = h1
        if fam_ok < 1:
            self.evidence.append(f"font families used: {sorted(set(fams))[:6]}")
        # spacing
        sp = a["spacing"]
        on_grid = sum(1 for v in sp if abs(v / 4 - round(v / 4)) * 4 <= 0.5)
        m["spacing_grid_rate"] = round(on_grid / len(sp), 4) if sp else 0.0
        # hygiene
        m["inline_handlers"] = a["inline_handlers"]
        m["inline_styles"] = a["inline_styles"]

    # ------------------------------------------------------------------ interactions
    def mobile_nav(self, browser):
        ctx, pg = self.page(browser, 375)
        try:
            link = 'header nav a[href="#pricing"]'
            toggle_vis = self.visible(pg, "#nav-toggle")
            hidden0 = not self.visible(pg, link)
            exp0 = pg.get_attribute("#nav-toggle", "aria-expanded") if toggle_vis else None
            opened = closed = False
            if toggle_vis:
                pg.click("#nav-toggle")
                pg.wait_for_timeout(400)
                opened = self.visible(pg, link) and pg.get_attribute("#nav-toggle", "aria-expanded") == "true"
                pg.click("#nav-toggle")
                pg.wait_for_timeout(400)
                closed = (not self.visible(pg, link)) and pg.get_attribute("#nav-toggle", "aria-expanded") == "false"
            parts = [toggle_vis, hidden0 and exp0 == "false", opened, closed]
            self.m["mobile_nav_score"] = sum(parts) / 4
            if not all(parts):
                self.evidence.append(f"mobile nav: toggle_visible={toggle_vis} hidden_initially={hidden0} "
                                     f"aria_expanded0={exp0} opens={opened} closes={closed}")
        finally:
            ctx.close()

    def desktop_nav(self, browser):
        ctx, pg = self.page(browser, 1280)
        try:
            ok = self.visible(pg, 'header nav a[href="#pricing"]') and not self.visible(pg, "#nav-toggle")
            ctx2, pg2 = self.page(browser, 768)
            try:
                ok768 = self.visible(pg2, 'header nav a[href="#pricing"]') and not self.visible(pg2, "#nav-toggle")
            finally:
                ctx2.close()
            self.m["desktop_nav_ok"] = (int(ok) + int(ok768)) / 2
            if not (ok and ok768):
                self.evidence.append(f"desktop nav links visible without toggle: 1280={ok} 768={ok768}")
        finally:
            ctx.close()

    def pricing(self, browser):
        ctx, pg = self.page(browser, 1280)
        try:
            sel = {p: f'section#pricing [data-plan="{p}"] [data-price]' for p in ("starter", "growth", "enterprise")}

            def prices():
                return {p: norm(pg.locator(s).first.inner_text()) for p, s in sel.items()}

            t = "#billing-toggle"
            if pg.locator(t).count() == 0 or any(pg.locator(x).count() == 0 for x in sel.values()):
                self.evidence.append("pricing: #billing-toggle or [data-plan] [data-price] elements missing")
                return
            p0 = prices()
            a0 = pg.get_attribute(t, "aria-checked")
            monthly0 = "$49" in p0["starter"] and "$199" in p0["growth"] and "custom" in p0["enterprise"] and a0 == "false"
            pg.click(t)
            pg.wait_for_timeout(200)
            p1 = prices()
            annual = "$39" in p1["starter"] and "$159" in p1["growth"] and "custom" in p1["enterprise"]
            aria1 = pg.get_attribute(t, "aria-checked") == "true"
            pg.click(t)
            pg.wait_for_timeout(200)
            p2 = prices()
            back = "$49" in p2["starter"] and "$199" in p2["growth"] and pg.get_attribute(t, "aria-checked") == "false"
            pg.focus(t)
            pg.keyboard.press("Space")
            pg.wait_for_timeout(200)
            kb = "$39" in prices()["starter"]
            parts = [monthly0, annual, aria1, back, kb]
            self.m["pricing_score"] = sum(parts) / len(parts)
            if not all(parts):
                self.evidence.append(f"pricing toggle: monthly_default={monthly0} annual={annual} aria={aria1} "
                                     f"back={back} keyboard={kb}; prices after toggle={p1}")
        finally:
            ctx.close()

    def faq(self, browser):
        ctx, pg = self.page(browser, 1280)
        try:
            buttons = pg.locator("section#faq button[aria-expanded][aria-controls]")
            n = buttons.count()
            results = []
            for i in range(min(n, 3)):
                b = buttons.nth(i)
                pid = b.get_attribute("aria-controls")
                panel = f"#{pid}"
                start = b.get_attribute("aria-expanded") == "false" and not self.visible(pg, panel)
                if i < 2:
                    b.click()
                else:
                    b.focus()
                    pg.keyboard.press("Enter")
                pg.wait_for_timeout(450)
                opened = b.get_attribute("aria-expanded") == "true" and self.visible(pg, panel)
                b.click()
                pg.wait_for_timeout(450)
                closed = b.get_attribute("aria-expanded") == "false" and not self.visible(pg, panel)
                results.append((start, opened, closed))
            flat = [x for r in results for x in r]
            self.m["faq_score"] = (sum(flat) / 9) if n >= 3 else 0.0
            if not flat or not all(flat):
                self.evidence.append(f"faq accordion (collapsed_initially, opens, closes) per item: {results} (buttons={n})")
        finally:
            ctx.close()

    def form(self, browser):
        ctx, pg = self.page(browser, 1280)
        try:
            f = "form#demo-form"
            url0 = pg.url
            needed = [f] + [f'{f} [name="{n}"]' for n in ("name", "email", "company", "team_size", "consent")]
            absent = [x for x in needed if pg.locator(x).count() == 0]
            if absent:
                self.evidence.append(f"form: required elements missing: {absent}")
                return
            before_non_get = len(self.non_get)
            submit = f'{f} [type="submit"], {f} button:not([type="button"]):not([type="reset"])'
            pg.locator(submit).first.click()
            pg.wait_for_timeout(300)
            required = ["name", "email", "company", "team_size", "consent"]

            def invalid(n):
                return pg.get_attribute(f'{f} [name="{n}"]', "aria-invalid") == "true"

            inv = [n for n in required if invalid(n)]
            blocked = pg.url == url0 and not self.visible(pg, "#form-status:not(:empty)")
            linked = 0
            for n in inv:
                ids = (pg.get_attribute(f'{f} [name="{n}"]', "aria-describedby") or "").split()
                texts = [norm(pg.locator(f"#{i}").first.inner_text()) for i in ids if pg.locator(f"#{i}").count() and self.visible(pg, f"#{i}")]
                if any(texts):
                    linked += 1
            focused = pg.evaluate("() => document.activeElement && document.activeElement.getAttribute('name')")
            focus_ok = focused == "name"
            # invalid email, everything else valid
            pg.fill(f'{f} [name="name"]', "Ada Lovelace")
            pg.fill(f'{f} [name="email"]', "not-an-email")
            pg.fill(f'{f} [name="company"]', "Analytical Engines Ltd")
            pg.select_option(f'{f} [name="team_size"]', index=2)
            try:
                pg.check(f'{f} [name="consent"]', timeout=3000)
            except Exception:
                self.evidence.append("form: clicking the consent checkbox did not toggle it (layout shift under the "
                                     "pointer?); toggled programmatically to continue")
                pg.evaluate("() => { const c = document.querySelector('form#demo-form [name=consent]'); if (c && !c.checked) c.click(); }")
            pg.locator(submit).first.click()
            pg.wait_for_timeout(300)
            bad_email = invalid("email") and not invalid("name") and not invalid("company")
            pg.fill(f'{f} [name="email"]', "ada@analytical.example")
            pg.locator(submit).first.click()
            pg.wait_for_timeout(500)
            status_text = norm(pg.locator("#form-status").first.inner_text()) if pg.locator("#form-status").count() else ""
            success = norm(SUCCESS_TEXT) in status_text and self.visible(pg, "#form-status")
            no_nav = pg.url.split("#")[0] == url0.split("#")[0] and len(self.non_get) == before_non_get
            parts = [blocked, len(inv) >= 5, linked >= len(required) and len(inv) >= 5, focus_ok, bad_email, success, no_nav]
            self.m["form_score"] = sum(parts) / len(parts)
            if not all(parts):
                self.evidence.append(f"form: blocks_empty={blocked} invalid_marked={inv} errors_linked={linked} "
                                     f"focus_first_invalid={focus_ok}({focused}) rejects_bad_email={bad_email} "
                                     f"success={success} no_navigation_or_network={no_nav}")
        finally:
            ctx.close()

    def keyboard(self, browser):
        ctx, pg = self.page(browser, 1280)
        try:
            focused_styles, unfocused_styles, order = {}, {}, []
            prev = None
            skip_ok = False
            for i in range(30):
                pg.keyboard.press("Tab")
                h = pg.evaluate_handle("() => document.activeElement")
                key = pg.evaluate("(el) => { if (!el || el === document.body) return null; if (!el.dataset.aibenchKey) el.dataset.aibenchKey = 'k' + Math.random().toString(36).slice(2); return el.dataset.aibenchKey; }", h)
                if key is None:
                    break
                st = pg.evaluate(FOCUS_STYLE_JS, h)
                if i == 0:
                    r = st["rect"]
                    skip_ok = st["href"] == "#main" and r[2] * r[3] > 4 and r[1] >= -1 and r[0] >= -1
                if key in focused_styles:
                    break
                focused_styles[key] = st
                order.append(key)
                if prev is not None:
                    unfocused_styles[prev] = pg.evaluate(FOCUS_STYLE_JS, prev_handle)
                prev, prev_handle = key, h
            if prev is not None:
                pg.evaluate("() => document.activeElement && document.activeElement.blur()")
                unfocused_styles[prev] = pg.evaluate(FOCUS_STYLE_JS, prev_handle)
            good = 0
            for k in order:
                f, u = focused_styles[k], unfocused_styles.get(k)
                ring = f["os"] not in ("none", "hidden") and f["ow"] >= 1 and (parse_color(f["oc"]) or (0, 0, 0, 0))[3] > 0
                changed = u is not None and any(f[x] != u[x] for x in ("outline", "shadow", "border", "bg", "deco"))
                good += 1 if (ring or changed) else 0
            self.m["focus_visible_rate"] = round(good / len(order), 4) if order else 0.0
            self.m["focusable_reached"] = len(order)
            self.m["skip_link_ok"] = 1 if skip_ok else 0
            if not skip_ok:
                self.evidence.append("first Tab does not focus a visible skip link to #main")
            if order and good < len(order):
                self.evidence.append(f"focus indicator missing on {len(order) - good}/{len(order)} focused elements")
        finally:
            ctx.close()

    def motion(self, browser):
        ctx, pg = self.page(browser, 1280, reduced=True)
        try:
            pg.wait_for_timeout(300)
            r = pg.evaluate(MOTION_JS)
            moving = [a for a in r["running"] if a["iterations"] == -1 or a["duration"] > 100]
            self.m["reduced_motion_ok"] = 1 if not moving and not r["smooth"] else 0
            if not self.m["reduced_motion_ok"]:
                self.evidence.append(f"with prefers-reduced-motion: {len(moving)} running animation(s), smooth_scroll={r['smooth']}")
        finally:
            ctx.close()


def lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def contrast(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def main():
    site, out, chromium = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    probe = Probe(site, out, chromium)
    try:
        res = probe.run()
        res["status"] = "ok"
    except Exception as e:
        res = {"status": "error", "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-4000:],
               "metrics": probe.m, "evidence": probe.evidence}
    res["duration_s"] = round(time.time() - t0, 2)
    (out / "result.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
