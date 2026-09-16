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

The script must:

1. Strip Framer badge markup, CSS, hydration, and the `__framer-badge` import
2. Rewrite title, description, canonical, Open Graph, Twitter, and JSON-LD from `site.meta.json`
3. Point `siteCanonicalURL` at `https://construct-zero.vercel.app`
4. Keep Framer runtime, fonts, page modules, and `#main` hydration untouched
5. Keep a new Framer `og:image` when it is not a known template screenshot

## Non-goals

- Do not restyle or rewrite page sections
- Do not remove Framer analytics, fonts, or the React bundle
- Do not add UI, watermarks, or extra routes on the live site
- `PREDEPLOY.md`, `site.meta.json`, `scripts/`, and `.cursor/` are excluded from the Vercel deploy via `.vercelignore`

## Workflow

1. Export the site from Framer as HTML
2. Replace `index.html` with that file
3. Run `python3 scripts/predeploy.py`
4. Hard-refresh local preview and confirm the badge is gone
5. Run `python3 scripts/predeploy.py --check`
6. Deploy

Edit SEO / AEO copy in `site.meta.json`, not in the Framer file.

## Pre-deploy checklist

- [ ] `index.html` is the latest Framer export
- [ ] `python3 scripts/predeploy.py` completed with no failures
- [ ] No `#__framer-badge-container` or `__framer-badge` in `index.html`
- [ ] `<title>`, `og:title`, and `twitter:title` are Construct Zero
- [ ] Description has no Atmos / climate / waitlist leftover
- [ ] Canonical and `og:url` are `https://construct-zero.vercel.app/`
- [ ] `siteCanonicalURL` is not a `framer.app` host
- [ ] JSON-LD includes WebSite, SoftwareApplication, and FAQPage
- [ ] Share image is the Construct Zero hero (or a newer Framer screenshot, not the Atmos template image)
- [ ] Homepage still hydrates: hero, FAQ, and View repository still work
- [ ] `python3 scripts/predeploy.py --check` exits 0

## Source of truth

| Field | File |
| --- | --- |
| Title, description, URL, FAQs | `site.meta.json` |
| Badge strip + metadata upsert | `scripts/predeploy.py` |
| Live page | `index.html` |
