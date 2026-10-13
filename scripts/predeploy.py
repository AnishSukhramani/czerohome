#!/usr/bin/env python3
"""Sanitize a Framer HTML export before Construct Zero deploys.

Usage:
  python3 scripts/predeploy.py          # rewrite index.html
  python3 scripts/predeploy.py --check  # verify only, exit 1 on failures
  python3 scripts/predeploy.py --check --strict  # fail if community CTA missing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
META_PATH = ROOT / "site.meta.json"

ANALYTICS_START = "<!-- cz:analytics:start -->"
ANALYTICS_END = "<!-- cz:analytics:end -->"

BANNED_BODY_TOKENS = (
    "__framer-badge",
    "__framer-badge-container",
    'import("__framer-badge")',
)

VERCEL_STUB = (
    '<script>window.va = window.va || function () { '
    "(window.vaq = window.vaq || []).push(arguments); };</script>"
)
VERCEL_SCRIPT = '<script defer src="/_vercel/insights/script.js"></script>'


def load_meta() -> dict:
    return json.loads(META_PATH.read_text())


def extract_attr(html: str, pattern: str) -> str | None:
    match = re.search(pattern, html, flags=re.I)
    return match.group(1).strip() if match else None


def choose_og_image(html: str, meta: dict) -> str:
    exported = extract_attr(html, r'<meta[^>]+(?:property|name)="og:image"[^>]+content="([^"]+)"')
    if not exported:
        exported = extract_attr(html, r'<meta[^>]+content="([^"]+)"[^>]+(?:property|name)="og:image"')
    banned = set(meta.get("bannedOgImages") or [])
    if exported and exported not in banned:
        return exported
    return meta["ogImage"]


def repo_url(meta: dict) -> str:
    return meta.get("repo_url") or meta["github"]


def env_analytics_override() -> bool | None:
    """Return True/False when CZ_ANALYTICS is set, else None."""
    raw = os.environ.get("CZ_ANALYTICS", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


def vercel_analytics_enabled(meta: dict) -> bool:
    override = env_analytics_override()
    if override is not None:
        return override
    analytics = meta.get("analytics") or {}
    return bool(analytics.get("vercel", False))


def umami_analytics_enabled(meta: dict) -> dict | None:
    analytics = meta.get("analytics") or {}
    umami = analytics.get("umami") or {}
    if not umami.get("enabled"):
        return None
    website_id = (umami.get("website_id") or "").strip()
    if not website_id:
        return None
    return umami


def analytics_inner_html(meta: dict) -> str:
    parts: list[str] = []
    if vercel_analytics_enabled(meta):
        parts.extend([VERCEL_STUB, VERCEL_SCRIPT])
    umami = umami_analytics_enabled(meta)
    if umami:
        src = umami.get("src") or "https://cloud.umami.is/script.js"
        wid = umami["website_id"]
        domains = umami.get("domains") or ""
        attrs = f'defer src="{src}" data-website-id="{wid}"'
        if domains:
            attrs += f' data-domains="{domains}"'
        parts.append(f"<script {attrs}></script>")
    return "\n    ".join(parts)


def analytics_block(meta: dict) -> str:
    inner = analytics_inner_html(meta)
    if not inner:
        return ""
    return "\n".join(
        [
            f"    {ANALYTICS_START}",
            f"    {inner}",
            f"    {ANALYTICS_END}",
        ]
    )


def strip_analytics_block(html: str) -> str:
    pattern = (
        r"[ \t]*<!-- cz:analytics:start -->.*?<!-- cz:analytics:end -->\s*"
    )
    return re.sub(pattern, "", html, flags=re.DOTALL)


def upsert_analytics(html: str, meta: dict) -> str:
    html = strip_analytics_block(html)
    block = analytics_block(meta)
    if not block:
        return html
    head_end = html.find("</head>")
    if head_end == -1:
        raise SystemExit("index.html is missing </head>")
    return html[:head_end] + "\n" + block + "\n" + html[head_end:]


def json_ld(meta: dict) -> str:
    repo = repo_url(meta)
    same_as: list[str] = [repo]
    demo = meta.get("demoVideoUrl")
    if demo:
        same_as.append(demo)

    software: dict = {
        "@type": "SoftwareApplication",
        "name": meta["name"],
        "applicationCategory": "DeveloperApplication",
        "operatingSystem": "macOS, Linux",
        "url": meta["siteUrl"] + "/",
        "description": meta["description"],
        "codeRepository": repo,
        "sameAs": same_as,
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
    }

    graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "name": meta["name"],
                "url": meta["siteUrl"] + "/",
                "description": meta["description"],
            },
            software,
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": item["question"],
                        "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
                    }
                    for item in meta["faq"]
                ],
            },
        ],
    }
    return json.dumps(graph, ensure_ascii=False, separators=(",", ":"))


def seo_block(meta: dict, og_image: str) -> str:
    title = meta["title"]
    description = meta["description"]
    name = meta["name"]
    url = meta["siteUrl"] + "/"
    locale = meta["locale"]
    return "\n".join(
        [
            f"\t<title>{title}</title>",
            f'    <meta name="description" content="{description}" />',
            f'    <meta name="application-name" content="{name}">',
            f'    <link rel="canonical" href="{url}">',
            '    <!-- Open Graph -->',
            '    <meta property="og:type" content="website">',
            f'    <meta property="og:site_name" content="{name}">',
            f'    <meta property="og:url" content="{url}">',
            f'    <meta property="og:title" content="{title}">',
            f'    <meta property="og:description" content="{description}">',
            f'    <meta property="og:image" content="{og_image}">',
            f'    <meta property="og:image:alt" content="{title}">',
            f'    <meta property="og:locale" content="{locale}">',
            "    <!-- X -->",
            '    <meta name="twitter:card" content="summary_large_image">',
            f'    <meta name="twitter:title" content="{title}">',
            f'    <meta name="twitter:description" content="{description}">',
            f'    <meta name="twitter:image" content="{og_image}">',
            f'    <meta name="twitter:image:alt" content="{title}">',
            '    <script type="application/ld+json">',
            f"    {json_ld(meta)}",
            "    </script>",
        ]
    )


SEO_LINE_MARKERS = (
    "<title",
    'name="description"',
    'name="application-name"',
    'rel="canonical"',
    "property=\"og:",
    "name=\"twitter:",
    "application/ld+json",
    "<!-- Open Graph",
    "<!-- X -->",
)


def is_seo_line(line: str) -> bool:
    lowered = line.lower()
    return any(marker.lower() in lowered for marker in SEO_LINE_MARKERS)


def strip_existing_seo(prefix: str) -> str:
    kept: list[str] = []
    skipping_ld = False
    for line in prefix.splitlines(keepends=True):
        if skipping_ld:
            if "</script>" in line:
                skipping_ld = False
            continue
        if "application/ld+json" in line:
            skipping_ld = "</script>" not in line
            continue
        if is_seo_line(line):
            continue
        kept.append(line)
    text = "".join(kept)
    return re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"


def upsert_seo(html: str, meta: dict) -> str:
    og_image = choose_og_image(html, meta)
    head_end = html.find("</head>")
    if head_end == -1:
        raise SystemExit("index.html is missing </head>")
    head, rest = html[:head_end], html[head_end:]

    importmap_at = re.search(r'[ \t]*<script type="importmap"', head)
    if not importmap_at:
        raise SystemExit("index.html is missing the Framer importmap")
    prefix, tail = head[: importmap_at.start()], head[importmap_at.start() :]
    prefix = strip_existing_seo(prefix)
    block = seo_block(meta, og_image) + "\n"
    generator = re.search(r'.*<meta name="generator"[^\n]*\n', prefix)
    if generator:
        prefix = prefix[: generator.end()] + block + prefix[generator.end() :]
    else:
        prefix = prefix + block
    return prefix + tail + rest


def remove_badge_css(html: str) -> str:
    html = re.sub(
        r"[ \t]*@supports \(z-index: calc\(infinity\)\) \{\s*"
        r"#__framer-badge-container \{[^}]*\}\s*\}\s*",
        "",
        html,
    )
    html = re.sub(
        r"[ \t]*#__framer-badge-container \{[^}]*\}\s*",
        "",
        html,
    )
    return html


def remove_badge_html(html: str) -> str:
    kept = []
    for line in html.splitlines(keepends=True):
        if 'id="__framer-badge-container"' in line or "id='__framer-badge-container'" in line:
            continue
        kept.append(line)
    return "".join(kept)


def remove_badge_js(html: str) -> str:
    html = re.sub(r'"__framer-badge":"[^"]+",', "", html)
    html = re.sub(
        r"\n[ \t]*;\(function \(\) \{[^\n]*\n(?:[^\n]*\n)*?[ \t]*"
        r"document\.getElementById\([\"']__framer-badge-container[\"']\)"
        r"(?:[^\n]*\n)*?[ \t]*\}\)\(\)\n",
        "\n",
        html,
    )
    return html


def fix_canonical_runtime(html: str, site_url: str) -> str:
    return re.sub(
        r'siteCanonicalURL:\s*"[^"]+"',
        f'siteCanonicalURL: "{site_url}"',
        html,
        count=1,
    )


def sanitize(html: str, meta: dict) -> str:
    html = remove_badge_css(html)
    html = remove_badge_html(html)
    html = remove_badge_js(html)
    html = upsert_seo(html, meta)
    html = upsert_analytics(html, meta)
    html = fix_canonical_runtime(html, meta["siteUrl"])
    return html


def parse_json_ld_from_head(head: str) -> dict | None:
    match = re.search(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
        head,
        flags=re.DOTALL,
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def software_application_from_ld(data: dict | None) -> dict | None:
    if not data:
        return None
    graph = data.get("@graph") or []
    for node in graph:
        if node.get("@type") == "SoftwareApplication":
            return node
    return None


def cta_warnings(html: str, meta: dict) -> list[str]:
    cta = meta.get("cta") or {}
    url = (cta.get("community_url") or "").strip()
    if not url:
        return []
    if url in html:
        return []
    label = cta.get("required_text") or "community CTA"
    return [f"Community CTA missing from HTML (expected {label} link to {url})"]


def issues(html: str, meta: dict, *, strict: bool) -> tuple[list[str], list[str]]:
    """Return (failures, warnings)."""
    failures: list[str] = []
    warnings: list[str] = []

    for token in BANNED_BODY_TOKENS:
        if token in html:
            failures.append(f"Framer badge leftover: {token}")
    head = html.split("</head>", 1)[0]
    for pattern in meta["templateLeakPatterns"]:
        if pattern.lower() in head.lower():
            failures.append(f"Template leak in <head>: {pattern}")
    if "strong-years-972506.framer.app" in html or re.search(
        r'siteCanonicalURL:\s*"[^"]*framer\.app', html
    ):
        failures.append("siteCanonicalURL still points at Framer")
    if meta["name"] not in head:
        failures.append("Construct Zero is missing from <head>")
    compact_head = head.replace(" ", "")
    if '"@type":"SoftwareApplication"' not in compact_head:
        failures.append("SoftwareApplication JSON-LD is missing")
    if '"@type":"FAQPage"' not in compact_head:
        failures.append("FAQPage JSON-LD is missing")
    if 'rel="canonical"' not in head and "rel='canonical'" not in head:
        failures.append("canonical link is missing")
    if f'property="og:url" content="{meta["siteUrl"]}/"' not in head:
        failures.append("og:url is not the Construct Zero site")

    ld = parse_json_ld_from_head(head)
    app = software_application_from_ld(ld)
    expected_repo = repo_url(meta)
    if app:
        if app.get("codeRepository") != expected_repo:
            failures.append(
                f"codeRepository is {app.get('codeRepository')!r}, expected {expected_repo!r}"
            )
        if app.get("operatingSystem") != "macOS, Linux":
            failures.append(
                f"operatingSystem is {app.get('operatingSystem')!r}, expected 'macOS, Linux'"
            )
        same_as = app.get("sameAs") or []
        if expected_repo not in same_as:
            failures.append("JSON-LD sameAs missing repo_url")
        demo = meta.get("demoVideoUrl")
        if demo and demo not in same_as:
            failures.append("JSON-LD sameAs missing demoVideoUrl")

    vercel_on = vercel_analytics_enabled(meta)
    umami_on = umami_analytics_enabled(meta) is not None
    has_markers = ANALYTICS_START in head and ANALYTICS_END in head
    if vercel_on or umami_on:
        if not has_markers:
            failures.append("Analytics enabled in meta/env but cz:analytics block is missing")
        if vercel_on and "/_vercel/insights/script.js" not in head:
            failures.append("Vercel analytics script missing while enabled")
        if umami_on and "data-website-id" not in head:
            failures.append("Umami script missing while enabled")
    else:
        if has_markers:
            failures.append("Analytics block present but analytics is disabled")
        if "/_vercel/insights/script.js" in head and not has_markers:
            failures.append("Vercel insights script outside cz:analytics markers")

    cta = cta_warnings(html, meta)
    if cta:
        if strict:
            failures.extend(cta)
        else:
            warnings.extend(cta)

    return failures, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify without writing")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat missing community CTA as a failure (default: warn only)",
    )
    args = parser.parse_args()

    if not INDEX.exists():
        print("index.html not found", file=sys.stderr)
        return 1
    if not META_PATH.exists():
        print("site.meta.json not found", file=sys.stderr)
        return 1

    meta = load_meta()
    original = INDEX.read_text()
    cleaned = sanitize(original, meta)
    found, warnings = issues(cleaned, meta, strict=args.strict)

    vercel_on = vercel_analytics_enabled(meta)
    umami_on = umami_analytics_enabled(meta) is not None

    print("Pre-deploy checklist")
    print(f"  badge removed:           {'yes' if '__framer-badge' not in cleaned else 'NO'}")
    print(f"  Construct Zero <title>:  {'yes' if meta['title'] in cleaned else 'NO'}")
    print(f"  canonical / og:url:      {meta['siteUrl']}/")
    print(f"  JSON-LD (AEO):           WebSite + SoftwareApplication + FAQPage")
    print(f"  codeRepository:          {repo_url(meta)}")
    print(
        f"  analytics (vercel/umami): {'on' if vercel_on else 'off'}/"
        f"{'on' if umami_on else 'off'}"
    )
    print(f"  Framer runtime kept:     {'yes' if 'data-framer-bundle' in cleaned else 'NO'}")

    if warnings:
        print("\nWarnings:")
        for item in warnings:
            print(f"  - {item}")

    if found:
        print("\nFailures:")
        for item in found:
            print(f"  - {item}")
        return 1

    if args.check:
        if cleaned != original:
            print("\nindex.html needs sanitizing. Run: python3 scripts/predeploy.py")
            return 1
        print("\nReady to deploy.")
        return 0

    if cleaned != original:
        INDEX.write_text(cleaned)
        print("\nUpdated index.html")
    else:
        print("\nindex.html already clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
