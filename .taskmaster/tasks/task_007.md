# Task ID: 7

**Title:** Implement route duplicate detection and merge-by-default

**Status:** pending

**Dependencies:** 4

**Priority:** high

**Description:** Make my_routes additive by default in both CLI and GUI and add duplicate detection UX.

**Details:**

Update route import and route add flows to increment num_assigned on duplicates by default rather than overwriting. Add a route-exists endpoint and inline warning/coverage hints on the My Routes page.

**Test Strategy:**

Add a new route, add the same route again, and import duplicates through CLI. Verify counts increment and warnings appear.

## Subtasks

### 7.1. Switch routes import default to merge

**Status:** pending  
**Dependencies:** None  

Change CLI route import behavior from overwrite to additive by default.

**Details:**

Existing num_assigned should increment by imported count in merge mode, with explicit replace mode still supported.

### 7.2. Switch GUI route add default to additive

**Status:** pending  
**Dependencies:** None  

Change /api/routes/add behavior.

**Details:**

If the route already exists by origin_id, dest_id, and aircraft_id, increment num_assigned instead of overwriting it. Return clear flash messaging.

### 7.3. Add route-exists endpoint

**Status:** pending  
**Dependencies:** None  

Implement duplicate-check API for routes.

**Details:**

Add GET /api/route-exists?origin=&dest=&aircraft= to return existing route match data for the current form selection.

### 7.4. Add duplicate warning UI

**Status:** pending  
**Dependencies:** None  

Show inline warning before merge.

**Details:**

Display route details and current assigned count, e.g. 'This route already exists (KHI → LHR with A340-200, 2 assigned). Add more aircraft to it?'

### 7.5. Show pair coverage hint

**Status:** pending  
**Dependencies:** None  

Surface current route coverage for selected hub-destination pair.

**Details:**

When hub and destination are selected, show which aircraft already serve that pair. Optionally show profitable alternatives if easy to implement safely.
