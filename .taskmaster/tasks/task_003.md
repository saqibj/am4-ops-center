# Task ID: 3

**Title:** Refactor extraction to support hub-only refresh

**Status:** pending

**Dependencies:** 2

**Priority:** high

**Description:** Preserve full rebuild extraction while adding a hub-scoped refresh mode that only updates selected origin hubs.

**Details:**

Modify extractors/routes.py to keep current full rebuild mode available explicitly, but add refresh_single_hub and refresh_hubs style flows. Hub refresh must not clear all route data or replace master tables. It should ensure the selected airport exists locally, delete only selected hub route_aircraft and route_demands rows, recompute only those hubs, and update my_hubs extraction status.

**Test Strategy:**

Run full rebuild path and single-hub refresh path against a test DB. Verify that refreshing one hub changes only that hub's extracted rows.

## Subtasks

### 3.1. Preserve full rebuild path

**Status:** pending  
**Dependencies:** None  

Keep the current full extraction behavior available for explicit replace mode.

**Details:**

Retain the current orchestration that recreates the full extracted dataset when the user explicitly requests a full rebuild.

### 3.2. Add single-hub refresh function

**Status:** pending  
**Dependencies:** None  

Implement refresh logic for one hub.

**Details:**

Add a function that validates one hub, ensures airport master data exists, deletes only that origin hub's route rows and demand rows, recomputes routes for the hub, reinserts them, and updates hub status fields.

### 3.3. Add multi-hub refresh function

**Status:** pending  
**Dependencies:** None  

Implement refresh logic for a list of hubs.

**Details:**

Add a wrapper flow for refreshing multiple hubs in one command or GUI action using the same selective deletion and recompute semantics.

### 3.4. Handle missing airport or master-data prerequisites

**Status:** pending  
**Dependencies:** None  

Add safe fallback and clear errors.

**Details:**

If airport is missing locally, fetch and upsert it. If aircraft master data is missing, fail clearly with guidance to run a full extract once.

### 3.5. Persist managed hub extraction status

**Status:** pending  
**Dependencies:** None  

Update my_hubs state during refresh operations.

**Details:**

Set statuses like running, ok, or error and persist last_extracted_at and last_extract_error where appropriate.
