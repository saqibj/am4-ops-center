# Phase 2 Flamegraph Analysis

## Methodology (read this first)

### Why HTTP `?profile=1` flamegraphs were misleading

1. **Starlette thread pool:** Dashboard routes are sync `def` handlers. FastAPI runs them in `anyio.to_thread.run_sync`. **pyinstrument’s profiler is installed on the asyncio thread**; the handler runs on a **worker thread**. The default HTML output therefore shows either a giant **`[await]`** node (`async_mode="enabled"`) or **asyncio event-loop / `[self]`** sampling (`async_mode="disabled"`), not the route body.
2. **Session wall time is still correct:** `session.duration` from pyinstrument (~17–22s) matched `ProfilingMiddleware` `total_ms` — the profiler saw the full wall clock, but **not** the Python stacks where the work happened.

### Authoritative profiles

Interactive flamegraphs were produced by calling each `page_*` handler **directly in-process** (same thread as the profiler) via `PRD/_profile_direct_pages.py`. Those stacks show real time in `base_context`, `get_db` → `ensure_route_aircraft_baseline_prices`, `fetch_all` / `Connection.execute` / `Cursor.fetchall`, and (where visible) Jinja `render`.

The files saved under `PRD/flamegraphs/*.html` are **copies of those `*-direct.html` profiles** (interpretable stacks). Older HTTP-captured HTML files were misleading and were replaced for this report.

### Screenshot note

No static PNG is checked in: the pyinstrument HTML is interactive. Open `PRD/flamegraphs/<page>.html` locally in a browser; expand the top node to see **`page_*` → `base_context` → `get_db` / `fetch_*` / Jinja**.

---

## Summary table

Values in **Total / DB / Non-DB** are from **`ProfilingMiddleware` logs** on warm **profile** requests (`?profile=1`) on 2026-04-07 against the local `am4_data.db` (session `909491` in the capture run). **Non-DB** is `total_ms - db_ms` as reported by the middleware.

| Page | Total (ms) | DB (ms) | Non-DB (ms) | Top bottleneck (direct pyinstrument) | Category |
|------|------------|---------|-------------|--------------------------------------|----------|
| /contributions | 17,900.6 | 7,588.4 | 10,312.2 | `base_context` → `get_db` / `ensure_route_aircraft_baseline_prices` / `fetch_*` | **F** (see below) |
| / (index) | 17,665.1 | 9,068.6 | 8,596.5 | Same pattern; `page_index` SQL + shared `base_context` | **F** |
| /hub-explorer | 16,849.7 | 7,381.7 | 9,468.0 | `base_context` + `_hubs_with_names` (large `fetch_all`) | **F** |
| /my-fleet | 15,134.2 | 5,974.7 | 9,159.5 | `base_context` + `page_my_fleet` queries; Jinja ~few ms | **F** |
| /buy-next?hub=LAX | 21,897.6 | 8,859.7 | 13,037.9 | `base_context` + `_origin_hub_iatas_for_fleet_plan` + `_saved_filters_bar_context` | **F** |
| /my-routes | 19,469.7 | 6,414.4 | 13,055.3 | Same DB stack; **Jinja `render` ~120ms** subtree (visible vs other pages) | **F** + **A** (Jinja secondary) |

**Category key**

- **F — Measurement / accounting / structure:** The dominant stacks are **still SQLite and SQLite-adjacent Python**, but a large share is **not counted as `db_ms`** by the middleware (see “Why ‘non-DB’ is inflated” below). HTTP pyinstrument did not show these frames until we profiled on the handler thread.

---

## Why “non-DB” is inflated (critical)

1. **`ensure_route_aircraft_baseline_prices` runs on a raw `sqlite3` connection before `instrument_connection()` is applied** in `get_db()` (`dashboard/db.py`). Those `UPDATE route_aircraft …` statements can take **seconds** on a large DB but **do not increment** `db_ms` in `ProfilingMiddleware`.
2. **`fetch_all` uses `conn.execute` (instrumented) but also `Cursor.fetchall()`**, which is **not** wrapped — time spent materializing large result sets can appear as “Python” in profiles and is **not** fully reflected in `db_ms`.
3. Therefore the Phase 2 table’s **Non-DB** column mixes **true** Python (e.g. `[dict(r) for r in rows]`, template rendering) with **misclassified SQLite** work.

---

## Verdict

The surprise “8–22s of Python” is largely **not** mysterious interpreter overhead: **direct pyinstrument** shows the wall clock in **`base_context`**, **`ensure_route_aircraft_baseline_prices`**, **`fetch_all` / `Connection.execute` / `Cursor.fetchall`**, and (on `/my-routes` only) a **modest** Jinja `render` subtree. **No meaningful time** appeared under the **`am4`** game package on the request path. **Profiling middleware** did not show up as a top cost; the flamegraph cost is dominated by **real request work** (and HTML generation of the flamegraph is tiny vs the request).

The **single highest-impact fix** is to **fix measurement and connection behavior**: (1) instrument **all** DB time consistently (including `ensure_route_aircraft_baseline_prices` and optionally `fetchall`), or move baseline updates so they are not repeated on **every** `get_db()`; (2) reduce redundant **`get_db()` / `base_context`** work per request (connection + migrations + hub freshness query) so the same SQLite work is not paid multiple times.

---

## Per-page findings

### /contributions

**Flamegraph:** [PRD/flamegraphs/contributions.html](flamegraphs/contributions.html)  
**Screenshot:** Open the HTML locally (interactive); top chain: `page_contributions` → `base_context` (~11.6s subtree) → `get_db` / `ensure_route_aircraft_baseline_prices` / `fetch_all` / `execute` / `fetchall`.

**Top 3 frames (subtree total time, direct profile):**

1. `page_contributions` — ~17.6s — page entry.
2. `base_context` — ~11.6s — route count + hub freshness SQL (`get_db` twice worth of work in tree).
3. `ensure_route_aircraft_baseline_prices` — ~3.9s per `get_db` instance in the tree — **baseline `UPDATE`s on raw connection** (not in middleware `db_ms`).

**Concentration:** Concentrated in **`base_context` + `get_db` path** — a good single area to optimize (not diffuse noise).

**am4 on path?** **No.**

**Jinja?** Template render is small relative to DB in this profile.

**Row → dict / models?** `fetch_all` includes `[dict(r) for r in cur.fetchall()]` — minor vs `execute`/`fetchall` in the tree.

**json.dumps?** Not a hotspot.

**Profiling middleware?** Not visible as a top frame; negligible vs request.

**Bottleneck category:** **F** (misclassified / duplicated SQLite + structural `base_context` cost).

**Recommendation:** Hoist or cache hub-freshness + route-count; avoid repeating `ensure_route_aircraft_baseline_prices` on every connection; count baseline `UPDATE` time in metrics.

---

### / (index)

**Flamegraph:** [PRD/flamegraphs/index.html](flamegraphs/index.html)

**Top 3 frames (subtree total time, direct profile):**

1. `page_index` — ~19.0s.
2. `base_context` — ~11.7s.
3. `ensure_route_aircraft_baseline_prices` / `fetch_all` / `execute` — large remainder of tree.

**Bottleneck category:** **F**

**Recommendation:** Same as contributions: shared `base_context` + per-connection baseline work dominates.

---

### /hub-explorer

**Flamegraph:** [PRD/flamegraphs/hub-explorer.html](flamegraphs/hub-explorer.html)

**Top 3 frames (subtree total time, direct profile):**

1. `page_hub_explorer` — ~15.8s.
2. `base_context` — ~10.5s.
3. `_hubs_with_names` — ~5.3s — **heavy `fetch_all`** for distinct hubs.

**Bottleneck category:** **F**

**Recommendation:** Cache or SQL-tune `_hubs_with_names`; align with `base_context` deduplication.

---

### /my-fleet

**Flamegraph:** [PRD/flamegraphs/my-fleet.html](flamegraphs/my-fleet.html)

**Top 3 frames (subtree total time, direct profile):**

1. `page_my_fleet` — ~14.2s.
2. `base_context` — ~10.5s.
3. `fetch_all` / `execute` / `fetchall` — list aircraft + shared context queries.

**Jinja:** ~7ms `render` node visible — small.

**Bottleneck category:** **F**

**Recommendation:** Same connection/context strategy; fleet-specific query tuning.

---

### /buy-next?hub=LAX

**Flamegraph:** [PRD/flamegraphs/buy-next-hub-lax.html](flamegraphs/buy-next-hub-lax.html)

**Top 3 frames (subtree total time, direct profile):**

1. `page_buy_next` — ~21.0s.
2. `base_context` — ~10.8s.
3. `_origin_hub_iatas_for_fleet_plan` — ~6.4s — **distinct origins query**.
4. `_saved_filters_bar_context` — ~3.8s — extra `get_db` + queries.

**Bottleneck category:** **F**

**Recommendation:** Reduce redundant `get_db()` inside `_saved_filters_bar_context` and `_origin_hub_iatas_for_fleet_plan` when `base_context` already opened a connection; consider caching hub lists.

---

### /my-routes

**Flamegraph:** [PRD/flamegraphs/my-routes.html](flamegraphs/my-routes.html)

**Top 3 frames (subtree total time, direct profile):**

1. `page_my_routes` — ~18.8s.
2. `base_context` — ~11.4s.
3. `_airports_with_iata` — ~3.7s — large airport list query.
4. Jinja `render` — **~120ms** subtree — **largest template cost** in the six pages.

**Bottleneck category:** **F** (primary) + **A** (Jinja — secondary but visible here).

**Recommendation:** Same DB deduplication; template size/complexity for `my_routes.html` worth a pass if shrinking response is a goal.

---

## Category tally (6 pages)

| Category | Count | Notes |
|----------|-------|--------|
| A — Jinja | 1 | Noticeable **`render`** time on `/my-routes` only |
| B — am4 package | 0 | **Not** on the hot path |
| C — Row → dict / models | 0 | `dict(row)` not a top-of-tree problem vs SQL |
| D — JSON/HTML serialization | 0 | `json.dumps` not hot |
| E — Logging / profiling | 0 | Middleware not a significant self-cost |
| F — Other / structural | 6 | **Thread-pool blind spot for HTTP pyinstrument**; **misclassified SQLite** (baseline updates, `fetchall`); **repeated `get_db` / `base_context` work** |

---

## Next-task recommendations

- **Task 1.5a — Metrics honesty:** Extend DB timing to cover **all** `sqlite3` time on the request path: wrap **before** `ensure_route_aircraft_baseline_prices`, or move baseline updates to startup / migration-only; optionally attribute **`cursor.fetchall`** time.
- **Task 1.5b — Connection / context:** Provide a **single** per-request connection (or cached hub-freshness + route count) so `base_context` and page handlers do not each pay **full** `get_db()` + baseline migration cost.
- **Task 1.5c — pyinstrument ergonomics:** Document that **`?profile=1` + default pyinstrument** does not sample **thread-pool** sync routes; use **direct-handler profiling** (`PRD/_profile_direct_pages.py`) or a multi-thread sampler (e.g. py-spy on supported Python builds) for dashboard work.
- **Task 1.5d — `/my-routes` template:** If response size matters, profile **`my_routes.html`** structure after DB fixes (category **A** showed up here).

---

## Surprises / double-checks

1. **HTTP flamegraphs looked “empty” for app code** — confirmed: **worker thread**, not asyncio thread.
2. **`ensure_route_aircraft_baseline_prices` dominates** multiple seconds per `get_db()` — and is **outside** `instrument_connection`, so **`db_ms` under-reports** true SQLite cost.
3. **py-spy** failed on this machine with **Python 3.14** (“Failed to find python version from target process”) — relied on **direct pyinstrument** instead.
4. **Concurrent profiling** once triggered **`database is locked`** on `/buy-next` (two overlapping long requests) — SQLite locking is a real operational constraint under parallel load.
