# Socialite responsive UPC — Implementation Plan

**Goal:** Implement the approved plan-first experience with a polished desktop/mobile frontend and verified UPC campus imagery.
**Architecture:** Progressive Jinja2 templates, shared responsive CSS and small discovery JavaScript. Keep the Flask application factory and authenticated connection/chat services.
**Tech Stack:** Flask, SQLAlchemy, Jinja2, CSS, JavaScript, existing Socket.IO.
**Spec:** `docs/superpowers/specs/2026-09-04-conecta-por-un-plan-design.md`, with user steering on 2026-09-07 prioritizing desktop/mobile presentation and UPC imagery.

## Constraints

- Real profile data and verified UPC sources; no fabricated members or availability.
- Preserve image storage, authentication, CSRF, blocking, and API matching scores.
- Existing user upload is untracked: do not commit or delete it.
- User has authorized implementation and GitHub publication. Proceed through verification without another design approval gate.

## Tasks

- [ ] Shared shell: `templates/base.html`, `templates/index.html`, `templates/panel.html`, `templates/persona.html`, `static/experience.css`, shared icons. Sidebar on desktop, five-item bottom navigation on mobile, clear responsive grids, actual campus image and fallback. Preserve all form fields and security links.
- [ ] Discovery: `templates/companeros.html`, `static/discovery.css`, `static/discovery.js`. One candidate at a time, previous/next/list controls, optional swipe to advance only, explicit confirmation for connection. Preserve filters, ranking details, no-JS list. Support `plan=estudio|proyecto|social`.
- [ ] Integration: `pages.py`, `companions.py`, `common.py` and pure discovery helper. Authenticated home redirects to rendered panel; explicit JSON remains available for panel/persona. Connect form context is server-generated and persisted using an additive migration, accepted only by recipient; chat draft is never auto-sent.
- [ ] UPC imagery/resources: verify official campus and cultural pages, link photographs with attribution, deterministic local fallback illustrations, links to official campus and Viernes Culturales resources. Document asset sources.
- [ ] Verification: integration tests for HTML/JSON, plan invitation and auth/CSRF; full existing suite once integrated. Inspect desktop 1440 and mobile 390/360 layouts, navigation, filters, next/previous, no-JS behavior, pending/accepted states. Fix actual failures. Ruff/mypy and independent review before commit.
- [ ] Delivery: safe database backup/migration if required; restart server; authenticated smoke; commit and push to main without overwriting concurrent remote changes. Report URL and verified limitations.

## Test commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m flask --app app:create_app db check
```

Use isolated SQLite for automated tests and test accounts for browser verification. Preview all routes with browser screenshots and check document width does not exceed viewport width. Existing tests expecting missing panel/persona templates are changed to test HTML by default and explicit JSON rather than removed.
