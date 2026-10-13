# Construct Zero — Pre-deploy PRD

This file is the shipping checklist for the marketing site. It is not part of the live page. After every Framer export, paste the new HTML into `index.html`, then run the sanitizer before deploy.

## Problem

The homepage is a Framer export dropped into a single `index.html`. Each paste brings back:

- The “Made in Framer” badge overlay
- Template SEO (Atmos / climate waitlist copy, `*.framer.app` canonical)
- Incomplete Open Graph and no answer-engine JSON-LD

Those leftovers should never ship. The Framer page itself must keep working.

## Goal

One local command that is safe to run after every paste:

```sh
python3 scripts/predeploy.py
```

Verify only (no write):

```sh
python3 scripts/predeploy.py --check
```

Treat a missing community CTA as a hard failure (for CI once Framer has the link):

```sh
python3 scripts/predeploy.py --check --strict
```

The script must:

1. Strip Framer badge markup, CSS, hydration, and the `__framer-badge` import
2. Rewrite title, description, canonical, Open Graph, Twitter, and JSON-LD from `site.meta.json`
3. Point `siteCanonicalURL` at `https://construct-zero.vercel.app`
4. Keep Framer runtime, fonts, page modules, and `#main` hydration untouched
5. Keep a new Framer `og:image` when it is not a known template screenshot
6. Optionally inject analytics between `<!-- cz:analytics:start -->` and `<!-- cz:analytics:end -->` (see below)
7. Warn when `cta.community_url` is not present in the HTML (Framer must add the CTA; predeploy does not add UI)

## Analytics (Vercel + optional Umami)

Analytics are **off by default** so local previews and deploys work before Vercel Web Analytics is enabled.

| Enable | How |
| --- | --- |
| Vercel | Set `"analytics": { "vercel": true, ... }` in `site.meta.json`, **or** run predeploy with `CZ_ANALYTICS=1` |
| Umami | Set `"umami": { "enabled": true, "website_id": "<id>", ... }` in `site.meta.json` |

When enabled, predeploy injects before `</head>`:

- **Vercel:** the `window.va` stub plus `<script defer src="/_vercel/insights/script.js"></script>`
- **Umami:** `<script defer src="…" data-website-id="…" data-domains="…"></script>`

**Before the first analytics-enabled deploy:** turn on **Web Analytics** in the Vercel project dashboard. If the feature is off, `/_vercel/insights/script.js` returns 404 in production.

Neither Vercel Web Analytics nor Umami uses cookies for this integration; no cookie banner is required for these scripts alone.

## JSON-LD

- `codeRepository` comes from `repo_url` in `site.meta.json` (the product repo, not this landing repo)
- `operatingSystem` is `macOS, Linux` (Windows is not listed until supported)
- `sameAs` includes `repo_url` and `demoVideoUrl` when set

## Non-goals

- Do not restyle or rewrite page sections
- Do not remove Framer analytics, fonts, or the React bundle
- Do not add UI, watermarks, or extra routes on the live site
- `PREDEPLOY.md`, `site.meta.json`, `scripts/`, `tests/`, `.github/`, and `.cursor/` are excluded from the Vercel deploy via `.vercelignore`

## Workflow

1. Export the site from Framer as HTML
2. Replace `index.html` with that file
3. Add or confirm the community CTA link in Framer (hero/footer → construct-zero Discussions)
4. Run `python3 scripts/predeploy.py`
5. Hard-refresh local preview and confirm the badge is gone
6. Run `python3 scripts/predeploy.py --check` (add `--strict` once the CTA is in Framer)
7. Deploy

Edit SEO / AEO copy in `site.meta.json`, not in the Framer file.

## Pre-deploy checklist

- [ ] `index.html` is the latest Framer export
- [ ] Community CTA in Framer points at construct-zero Discussions
- [ ] `python3 scripts/predeploy.py` completed with no failures
- [ ] No `#__framer-badge-container` or `__framer-badge` in `index.html`
- [ ] `<title>`, `og:title`, and `twitter:title` are Construct Zero
- [ ] Description has no Atmos / climate / waitlist leftover
- [ ] Canonical and `og:url` are `https://construct-zero.vercel.app/`
- [ ] `siteCanonicalURL` is not a `framer.app` host
- [ ] JSON-LD includes WebSite, SoftwareApplication (repo = construct-zero), and FAQPage
- [ ] Share image is the Construct Zero hero (or a newer Framer screenshot, not the Atmos template image)
- [ ] Homepage still hydrates: hero, FAQ, and View repository still work
- [ ] If shipping analytics: Vercel Web Analytics enabled in the dashboard; `site.meta.json` or `CZ_ANALYTICS=1`
- [ ] `python3 scripts/predeploy.py --check` exits 0

## Source of truth

| Field | File |
| --- | --- |
| Title, description, URL, FAQs, analytics, CTA, repo | `site.meta.json` |
| Badge strip + metadata + analytics upsert | `scripts/predeploy.py` |
| Live page | `index.html` |

## CI

Pull requests run `python3 -m unittest discover -s tests` and `python3 scripts/predeploy.py --check` (read-only; no deploy).
