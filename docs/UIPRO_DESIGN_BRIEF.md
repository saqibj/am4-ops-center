# AM4 Ops Center — UI architecture audit & UIPRO design brief

**Date:** 2026-04-04  
**Stack (as implemented):** FastAPI + Jinja2 + HTMX + Tailwind (Play CDN) + Chart.js + Leaflet  
**Not in use:** React, Next.js, SPA routers, CSS Modules

This document is the **implementation impact list** and **UIPRO-ready brief** for the settings, theming, branding, and table-readability work described in Taskmaster task 2+.

---

## 1. Current architecture (audit summary)

### 1.1 App shell & layout

| Concern | Location | Notes |
|--------|----------|--------|
| Root HTML, `<head>`, script/CSS includes | `dashboard/templates/base.html` | Tailwind via CDN; HTMX, Chart.js, Leaflet; minimal inline styles for HTMX indicators |
| Document theme | `base.html` `<html class="dark">` | **Hard-coded dark**; no `prefers-color-scheme` or user toggle |
| Sidebar + mobile nav | `base.html` | Checkbox “peer” pattern; fixed nav `w-64`, overlay on small screens |
| Product title | `base.html` | `<h1>AM4 Ops Center</h1>` — **primary branding slot** |
| Main content | `base.html` `{% block content %}` | `main` with padding; all pages extend `base.html` |
| DB meta footer | `base.html` nav bottom | `db_name`, `route_count` from `base_context` |

### 1.2 Routing

| Layer | Location | Notes |
|-------|----------|--------|
| App factory & static mount | `dashboard/server.py` | `FastAPI`, `/static`, includes `pages` + `api_routes` routers |
| Full pages (HTML) | `dashboard/routes/pages.py` | Paths: `/`, `/hub-explorer`, `/aircraft`, `/route-analyzer`, `/fleet-planner`, `/buy-next`, `/my-fleet`, `/my-hubs`, `/my-routes`, `/contributions`, `/heatmap` |
| Short redirects | `dashboard/server.py` | `/hub` → `/hub-explorer`, `/route` → `/route-analyzer`, etc. |
| HTMX fragments & APIs | `dashboard/routes/api_routes.py` | Large router under `/api/*` returning HTML partials + some JSON |

**Settings route:** **Does not exist yet.** Natural placement: new handler in `pages.py` (e.g. `GET /settings`) and template `dashboard/templates/settings.html` extending `base.html`, plus a nav link in `base.html`.

### 1.3 Server context (every page)

| Function | Location | Injected keys |
|----------|----------|---------------|
| `base_context` | `dashboard/db.py` | `request`, `db_name`, `route_count` |

All page handlers merge this with page-specific data. Theme/branding settings can be passed from the same place **once** they are read from cookies or defaults (optional server-side); browser `localStorage` is more typical for this product’s settings model without backend changes.

### 1.4 Client-side state & persistence

| Mechanism | Status |
|-----------|--------|
| `localStorage` / `sessionStorage` / IndexedDB in `dashboard/` | **None found** |
| `dashboard/static/js/app.js` | **Placeholder comment only** — no app logic |
| Python `UserConfig` | `config.py` — **extraction/calculation** settings (game mode, fuel, hubs filter, etc.), **not** dashboard UI or theme |

**Impact:** Appearance, theme mode, airline name/logo, density, and notification toggles will need a **new** client persistence layer (recommended: `localStorage` + small vanilla JS module loaded from `base.html`, applied before paint for theme to avoid flash).

### 1.5 Styling system

- **Tailwind utility classes** throughout templates; **no** shared CSS variable layer for semantic colors today.
- **Dominant palette:** `gray-800/900`, `gray-100/300/400`, `emerald-400` accents, borders `gray-600/700`.
- **Charts/maps:** Chart.js canvases and Leaflet tiles will need **theme-aware** container/contrast choices when light mode is added.

### 1.6 Tables (banding / density targets)

All major data tables use the same general pattern: `table` + `thead` with `bg-gray-700 text-gray-300` + `tbody` with `divide-y divide-gray-700`. **No alternating row bands** today.

| Partial / page | File |
|----------------|------|
| Overview top routes | `dashboard/templates/index.html` |
| Hub inventory | `dashboard/templates/partials/hub_inventory.html` |
| Route table | `dashboard/templates/partials/route_table.html` |
| Aircraft table | `dashboard/templates/partials/aircraft_table.html` |
| Fleet inventory | `dashboard/templates/partials/fleet_inventory.html` |
| Fleet plan | `dashboard/templates/partials/fleet_plan_table.html` |
| Route compare | `dashboard/templates/partials/route_compare_table.html` |
| Contributions | `dashboard/templates/partials/contributions_table.html` |
| My routes inventory | `dashboard/templates/partials/my_routes_inventory.html` |

**Impact:** Prefer **one** reusable approach (e.g. Tailwind `even:bg-*` on `tr`, or CSS variables for row band colors) applied via a **macro** or **base partial** include to avoid nine divergent copies.

### 1.7 Assets

- **Favicon:** `dashboard/static/favicon.ico` (referenced from `base.html`).
- **No** dedicated app logo components; product name is text-only in the nav.

---

## 2. Implementation impact list (files & systems)

**Must touch for shell + theme + settings entry**

1. `dashboard/templates/base.html` — `<html>` class strategy, optional inline boot script for theme, nav link to Settings, airline/app branding slots, optional density class on `body`.
2. `dashboard/static/js/app.js` (or new `settings.js` / `theme.js`) — read/write settings, `prefers-color-scheme` listener, apply theme class, optional default landing redirect.
3. `dashboard/routes/pages.py` — register `/settings` (and optionally server-side defaults later).
4. `dashboard/templates/settings.html` — new page (sections: Appearance, Branding, Preferences, Notifications, Data/Reset, About).

**Should touch for tables**

5. All table partials listed in §1.6 (+ any tables inside full pages not using partials — verify `grep` during implementation).

**May touch for branding display**

6. `dashboard/templates/index.html` — welcome/overview headline area for **Airline Name** and optional welcome copy.
7. `dashboard/templates/base.html` — header/sidebar area for **Airline Logo** + name (per UIPRO layout).

**Low priority for initial theme pass**

8. Chart.js / Leaflet — ensure legends, tooltips, and map controls remain readable in light theme (may need Chart.js `color` options or CSS filters only if needed).

**Out of scope for “dashboard UI settings” unless explicitly extended**

9. `config.py` / `UserConfig` — keep separate from **dashboard appearance** unless product decision merges “game” and “UI” settings.

---

## 3. UIPRO design brief (what to design)

### 3.1 Product context

AM4 Ops Center is a **dense, data-heavy** operations dashboard for airline/route analysis. Users spend long sessions in **tables**, **filters**, and **maps**. Visual design should prioritize **scannability**, **contrast**, and **calm** chrome—not decorative noise.

### 3.2 App shell

- **Sidebar:** Keep existing information architecture (Overview, tools, My Airline group). Add **Settings** (gear or label) in a predictable place (footer of nav or below main groups).
- **Mobile:** Preserve hamburger + overlay; ensure Settings and theme do not require desktop-only interactions.
- **Header area:** Decide whether **airline branding** (name + logo) lives in **sidebar top** (replacing or complementing “AM4 Ops Center”), **main sticky bar**, or **both** (sidebar mark + overview welcome). UIPRO should pick **one primary** identity location to avoid duplication clutter.
- **Default app identity:** “AM4 Ops Center” remains as product name; **airline name** is user-supplied personalization.

### 3.3 Themes (Light / Dark / System)

- **Dark:** Evolve from current gray/emerald language; maintain emerald as **accent** only.
- **Light:** Surfaces should not be pure white everywhere; use **soft neutrals** for cards and sidebar; keep **WCAG AA** text contrast on tables.
- **System:** Resolved from `prefers-color-scheme` when user selects System; **live switch** when OS theme changes.
- **No flash:** Design assumes a tiny boot script sets `class` on `<html>` before first paint (implementation detail).

**Deliverables from UIPRO:** Color tokens (background tiers, border, text primary/secondary/muted, accent, danger/success if needed), sidebar + main surface treatment for **both** themes.

### 3.4 Settings page

- **Layout:** Sectioned UI (tabs, left nav, or stacked cards). Must work on **narrow** viewports.
- **Sections:** Appearance (theme, UI density), Branding (airline name, logo upload + preview), Preferences (default landing page, optional hub default if product keeps it), Notifications (toggles), Data/Reset, About.
- **Interaction model:** **Save / Cancel**, dirty-state awareness, section or global reset—not silent auto-save per keystroke (per PRD/tasks).
- **Preview:** Inline **mini shell preview** or **live** preview of theme + branding in a constrained frame.

### 3.5 Branding

- **Airline name:** Short line in shell + welcome; handle **long names** (truncate, tooltip, or wrap rules).
- **Airline logo:** Upload, preview, replace, remove; **safe areas** in sidebar/header; **fallback** to default app mark when empty.
- **Default logos:** Separate assets or SVG marks for **light** vs **dark** app branding (not only airline).

### 3.6 Tables

- **Banded rows** on all major tables; bands must **not** fight **hover**, **selection** (if added), or **status** colors.
- **Compact vs comfortable** density: spacing scale for row height, cell padding, and header height.
- **Horizontal scroll:** Several tables already use `min-w-[...]`; banding and sticky header behavior should be specified for scroll containers.

### 3.7 Responsive states

- Breakpoints: align with Tailwind defaults (`sm`, `md`, `lg`) unless UIPRO specifies otherwise.
- **Sidebar → drawer** behavior already exists; document focus rings and hit targets for touch.

---

## 4. Open decisions for UIPRO / product

1. **Single vs dual branding:** Is “AM4 Ops Center” always visible alongside airline name, or does airline replace the sidebar title when set?
2. **Default landing:** Which routes are valid first-load targets (likely `/` and key tools only).
3. **Notification toggles:** In-app only for now — UI still needs **clear on/off** patterns even if behavior is stubbed.
4. **Optional “default hub”:** Only if hub-aware routing is stable; current app uses hub selectors per page rather than a single global hub.

---

## 5. Next step (Task 2.6)

**Done:** Structured visual direction is in **[UIPRO_VISUAL_SPEC.md](./UIPRO_VISUAL_SPEC.md)** (tokens, shell, Settings layout, branding rules, tables, a11y). Implementation tasks 3+ should follow that spec; optional Figma can mirror it later if needed.
