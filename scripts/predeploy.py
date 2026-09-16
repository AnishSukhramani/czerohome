#!/usr/bin/env python3
"""Sanitize a Framer HTML export before Construct Zero deploys.

Usage:
  python3 scripts/predeploy.py          # rewrite index.html
  python3 scripts/predeploy.py --check  # verify only, exit 1 on failures
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
META_PATH = ROOT / "site.meta.json"

BANNED_BODY_TOKENS = (
    "__framer-badge",
    "__framer-badge-container",
    'import("__framer-badge")',
)


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


def json_ld(meta: dict) -> str:
    graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "name": meta["name"],
                "url": meta["siteUrl"] + "/",
                "description": meta["description"],
            },
            {
                "@type": "SoftwareApplication",
                "name": meta["name"],
                "applicationCategory": "DeveloperApplication",
                "operatingSystem": "macOS, Linux, Windows",
                "url": meta["siteUrl"] + "/",
                "description": meta["description"],
                "codeRepository": meta["github"],
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
            },
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
    html = fix_canonical_runtime(html, meta["siteUrl"])
    return html


def issues(html: str, meta: dict) -> list[str]:
    found = []
    for token in BANNED_BODY_TOKENS:
        if token in html:
            found.append(f"Framer badge leftover: {token}")
    head = html.split("</head>", 1)[0]
    for pattern in meta["templateLeakPatterns"]:
        if pattern.lower() in head.lower():
            found.append(f"Template leak in <head>: {pattern}")
    if "strong-years-972506.framer.app" in html or re.search(
        r'siteCanonicalURL:\s*"[^"]*framer\.app', html
    ):
        found.append("siteCanonicalURL still points at Framer")
    if meta["name"] not in head:
        found.append("Construct Zero is missing from <head>")
    compact_head = head.replace(" ", "")
    if '"@type":"SoftwareApplication"' not in compact_head:
        found.append("SoftwareApplication JSON-LD is missing")
    if '"@type":"FAQPage"' not in compact_head:
        found.append("FAQPage JSON-LD is missing")
    if 'rel="canonical"' not in head and "rel='canonical'" not in head:
        found.append("canonical link is missing")
    if f'property="og:url" content="{meta["siteUrl"]}/"' not in head:
        found.append("og:url is not the Construct Zero site")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify without writing")
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
    found = issues(cleaned, meta)

    print("Pre-deploy checklist")
    print(f"  badge removed:           {'yes' if '__framer-badge' not in cleaned else 'NO'}")
    print(f"  Construct Zero <title>:  {'yes' if meta['title'] in cleaned else 'NO'}")
    print(f"  canonical / og:url:      {meta['siteUrl']}/")
    print(f"  JSON-LD (AEO):           WebSite + SoftwareApplication + FAQPage")
    print(f"  Framer runtime kept:     {'yes' if 'data-framer-bundle' in cleaned else 'NO'}")

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
