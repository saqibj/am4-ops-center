# Task ID: 1

**Title:** Baseline audit and safety setup

**Status:** pending

**Dependencies:** None

**Priority:** high

**Description:** Verify the current repo state before making changes and establish non-destructive implementation guard rails.

**Details:**

Inspect the current routed pages, confirm there is no actual /buy-next page, confirm overwrite behavior in my_fleet and my_routes, and confirm full-refresh extractor behavior. Create a working branch and document guard rails for all later work.

**Test Strategy:**

Run python main.py --help and python main.py dashboard --help. Confirm current dashboard routes load and note missing /buy-next route.

## Subtasks

### 1.1. Confirm current routed pages and nav entries

**Status:** pending  
**Dependencies:** None  

Inspect pages.py and base.html to confirm real UI routes and left-nav items.

**Details:**

Document the current pages: /, /hub-explorer, /aircraft, /route-analyzer, /fleet-planner, /my-fleet, /my-routes, /contributions, /heatmap. Confirm left nav matches those routes.

### 1.2. Confirm missing Buy Next page

**Status:** pending  
**Dependencies:** None  

Verify README mismatch against real routed UI.

**Details:**

Confirm there is no actual /buy-next page or route implementation despite README mention.

### 1.3. Confirm overwrite behavior in fleet and routes

**Status:** pending  
**Dependencies:** None  

Inspect current conflict handling for my_fleet and my_routes.

**Details:**

Verify that commands/airline.py and dashboard/routes/api_routes.py currently overwrite quantity and num_assigned on conflict instead of incrementing.

### 1.4. Confirm extractor full-refresh behavior

**Status:** pending  
**Dependencies:** None  

Inspect route extraction orchestration.

**Details:**

Verify extractors/routes.py currently creates schema, clears route tables, replaces master tables, and recomputes everything.
