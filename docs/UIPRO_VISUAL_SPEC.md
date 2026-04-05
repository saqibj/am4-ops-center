# AM4 Ops Center — UIPRO visual specification

**Status:** Design direction (structured spec; no Figma file)  
**Stack:** Jinja2 + HTMX + Tailwind (CDN)  
**Companion:** [UIPRO_DESIGN_BRIEF.md](./UIPRO_DESIGN_BRIEF.md) (architecture audit)

---

## 1. Product & style direction

| Dimension | Choice |
|-----------|--------|
| **Product type** | Dense B2B / prosumer **operations dashboard** |
| **Visual personality** | **Calm professional** — neutral surfaces, one accent (emerald), no glassmorphism or heavy gradients |
| **Density default** | **Comfortable** for first load; **Compact** tightens vertical rhythm only (not font size below 14px body) |
| **Motion** | Subtle: 150–200ms for drawer overlay; avoid decorative animation on tables |

**Anti-patterns:** Neon accents, low-contrast gray-on-gray body text, pure `#ffffff` page background in light mode, more than one “hero” branding block on screen at once.

---

## 2. Resolved product decisions (from brief §4)

1. **Branding hierarchy:** **Dual, with clear primary.** Sidebar top shows **product** identity always: wordmark “AM4 Ops Center” (or small app logo + short name). **Airline name** appears as a **subtitle** line under it (`text-sm`, muted) when set; **airline logo** is a **small mark** (32–40px) **left of** the product title block, not a second page title. **Overview** page gets a **welcome line**: “Welcome back — {Airline Name}” (or generic copy if unset). This avoids replacing the product name while still personalizing.

2. **Default landing routes:** `/` (Overview), `/hub-explorer`, `/route-analyzer`, `/fleet-planner`, `/my-fleet`, `/my-routes`, `/my-hubs` — only stable top-level pages; no fragment-only URLs.

3. **Notifications:** Toggles use **switch** pattern with visible label + short description; stub behavior is OK if copy says “Alerts will apply to future features.”

4. **Default hub:** **Omit** from v1 settings unless hub-prefixed routing exists globally. Per-page hub selectors stay as today.

---

## 3. Semantic tokens (CSS variables)

Map these on `<html>` (or `<body>`) and reference in Tailwind via arbitrary values or a thin custom CSS layer. **Implementation can use `data-theme="light|dark"`** plus class `dark` mirroring resolved theme for Tailwind `dark:` if you migrate to a build step later; with CDN Tailwind, **prefer variables + light/dark classes on `html`** set by boot script.

### 3.1 Core palette

**Dark (default — evolution of current UI)**

| Token | Role | Suggested value |
|-------|------|-----------------|
| `--surface-page` | App background | `#0f1419` (near gray-900, slight blue) |
| `--surface-raised` | Cards, main panels | `#1a1f26` |
| `--surface-sunken` | Table header, inputs | `#252b33` |
| `--border-subtle` | Dividers, borders | `#3d4550` |
| `--text-primary` | Body, table main | `#e6e9ef` |
| `--text-secondary` | Labels, nav inactive | `#9aa3b2` |
| `--text-muted` | Hints, footer | `#6b7280` |
| `--accent` | Links, focus ring, positive highlights | `#34d399` (emerald-400) |
| `--accent-muted` | Hover backgrounds | `rgba(52, 211, 153, 0.12)` |
| `--row-a` | Table band A | transparent or same as raised |
| `--row-b` | Table band B | `rgba(255,255,255,0.03)` |
| `--row-hover` | Row hover | `rgba(52, 211, 153, 0.08)` |

**Light**

| Token | Role | Suggested value |
|-------|------|-----------------|
| `--surface-page` | App background | `#f0f2f5` (not pure white) |
| `--surface-raised` | Cards, panels | `#ffffff` |
| `--surface-sunken` | Table header | `#e8eaee` |
| `--border-subtle` | Borders | `#d1d5db` |
| `--text-primary` | Body | `#111827` |
| `--text-secondary` | Secondary | `#4b5563` |
| `--text-muted` | Muted | `#9ca3af` |
| `--accent` | Accent | `#059669` (emerald-600; darker for AA on white) |
| `--accent-muted` | Hover wash | `rgba(5, 150, 105, 0.10)` |
| `--row-a` | Band A | `#ffffff` |
| `--row-b` | Band B | `#f3f4f6` |
| `--row-hover` | Row hover | `rgba(5, 150, 105, 0.12)` |

**System:** Resolved theme = `light` or `dark` from `prefers-color-scheme` when user setting is `system`.

### 3.2 Typography

| Use | Spec |
|-----|------|
| **Font stack** | `ui-sans-serif, system-ui, sans-serif` (Tailwind default) |
| **Page title** (h2 in main) | `text-2xl font-bold`, `text-primary` |
| **Section title** (Settings) | `text-lg font-semibold` |
| **Body** | `text-sm` or `text-base` on Overview; keep tables at `text-sm` |
| **Numeric / tables** | `font-mono` or `tabular-nums` for profit, counts, IATA codes |

---

## 4. App shell layout

### 4.1 Sidebar (desktop `lg+`)

```
┌─────────────────────────┐
│ [app logo 32px]  AM4    │  ← product lockup; airline logo slot optional left
│ Ops Center              │  ← h1 / wordmark, one line break OK
│ SkyJet Airways          │  ← airline name; muted; hidden if empty
├─────────────────────────┤
│ Overview                │
│ Hub Explorer            │
│ ...                     │
│ MY AIRLINE              │  ← existing section label style
│ My Fleet                │
├─────────────────────────┤
│ ⚙ Settings              │  ← new; same row height as nav links
├─────────────────────────┤
│ DB: …                   │  ← existing meta footer
│ N routes                │
└─────────────────────────┘
```

- **Width:** Keep `w-64`; padding `p-4`.
- **Active route:** Left border accent (`border-l-2 border-accent pl-2`) or `bg-surface-sunken` — pick one pattern app-wide.
- **Focus:** `focus-visible:ring-2 ring-accent ring-offset-2` on all nav links (offset uses page bg).

### 4.2 Mobile (`<lg`)

- Hamburger unchanged; **Settings** appears in the **same drawer list** above the DB footer (not only on desktop).
- Overlay: `bg-black/50`; drawer slides from left; first focusable on open = close affordance or first link (document in implementation).

### 4.3 Main content

- Keep `main` scroll; **no sticky app header** in v1 (reduces duplication with sidebar). Page titles stay in each template’s `content` block.
- Optional future: thin **context bar** under `lg` only — out of scope unless tables need sticky filters globally.

---

## 5. Settings page

### 5.1 Layout pattern

- **`lg+`:** Two columns — **left rail** `w-56` sticky section links (anchor scroll or show one section at a time); **right** content `max-w-3xl`.
- **`<lg`:** Single column — **accordion** or **stacked cards** with clear section headings; section nav becomes a **select** or top **horizontal scroll chips**.

### 5.2 Section order & content

| # | Section | Contents |
|---|---------|----------|
| 1 | **Appearance** | Theme: Light / Dark / System (segmented control or radio cards). UI density: Comfortable / Compact. |
| 2 | **Branding** | Airline name (text, max length 60). Logo: upload, preview (contain, max-h-24), Replace, Remove, Reset to default. |
| 3 | **Preferences** | Default landing page (select of allowed routes). |
| 4 | **Notifications** | 2–3 switches with label + one-line help. |
| 5 | **Data & reset** | “Reset appearance”, “Reset branding”, “Reset all settings” with confirm for destructive actions. |
| 6 | **About** | App name, version placeholder, link to repo/docs if desired. |

### 5.3 Footer action bar (sticky bottom on long pages)

- **Cancel** (secondary) + **Save changes** (primary, accent background).
- **Dirty state:** Enable Save when form differs from last saved snapshot; Cancel reverts to snapshot.
- **Unsaved navigation:** Browser `beforeunload` + in-app link interception for HTMX/full navigation where feasible.

### 5.4 Live preview block

- **Placement:** Top of right column on `lg+`, below Appearance on mobile.
- **Content:** Mini **fake sidebar** (120px) + **fake main** strip showing product name, airline subtitle, and sample table **3 rows** with banding + hover — reflects current **draft** theme/density/branding (not saved state until Save).

---

## 6. Tables (banding, density, scroll)

### 6.1 Banded rows

- Apply to `tbody tr`: **odd** = `--row-a`, **even** = `--row-b` (or `even:bg-*` equivalents).
- **Hover:** `tr:hover` → `--row-hover` (must sit above band).
- **Do not** band header; keep `thead` `--surface-sunken` with **bottom border** `--border-subtle`.
- **Status / heat cells:** If a cell has a strong background (e.g. profit heat), **that cell** keeps its semantic bg; row band shows in other cells (implementation: optional `td` level banding skip — document if complex).

### 6.2 Density

| Mode | `th`/`td` padding | Row min-height |
|------|-------------------|----------------|
| Comfortable | `px-3 py-2.5` | ~40px |
| Compact | `px-2 py-1.5` | ~32px |

Apply via class on `table` or wrapper: `table-density-comfortable` / `table-density-compact` (BEM-style) mapping to utilities.

### 6.3 Horizontal scroll

- Wrapper: `overflow-x-auto rounded-lg border border-[var(--border-subtle)]`.
- **Sticky header:** `thead th { position: sticky; top: 0; z-index: 1; background: var(--surface-sunken); }` inside scroll container.

---

## 7. Branding & logos

| Asset | Dark theme | Light theme |
|-------|------------|-------------|
| **Default app logo** | SVG/PNG tuned for dark bg | Separate file for light sidebar |
| **Airline logo** | User upload; preview on neutral checkerboard only in Settings | Same |

**Sidebar mark:** `h-8 w-auto max-w-[140px] object-contain`; if image fails, show initials from airline name or generic icon.

---

## 8. Forms & settings controls

- **Segmented theme control:** Three options with icons (sun / moon / monitor).
- **Switches:** `role="switch"` + `aria-checked`; 44px min touch target on mobile.
- **File upload:** Drag zone + button; show **file name + size**; errors inline in `text-red-600` / dark equivalent (`red-400`).

---

## 9. Charts & maps (theme)

- **Chart.js:** Pass `color` for ticks/grid from CSS variables read in JS after theme change; on theme toggle, **destroy + recreate** or update options (implementation detail).
- **Leaflet:** Keep default tiles; ensure **control bar** sits on `--surface-raised` with border so it does not float on raw map in light mode.

---

## 10. Accessibility checklist

- [ ] All interactive elements keyboard reachable; visible `:focus-visible` outline (accent).
- [ ] Theme and density changes announce via **live region** (`aria-live="polite"`) optional.
- [ ] Settings preview region `aria-label="Appearance preview"`.
- [ ] Table sort controls (if any buttons) retain `aria-sort` where applicable.

---

## 11. Implementation order (for devs)

1. CSS variables + `html` class boot (no flash).  
2. Refactor `base.html` shell to tokens.  
3. Settings route + layout + Save/Cancel + preview strip.  
4. Table wrapper + banding + density classes across partials.  
5. Chart.js / Leaflet theme hookup.

---

*End of UIPRO visual spec.*
