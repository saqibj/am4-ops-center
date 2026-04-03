# Task ID: 9

**Title:** Implement hub freshness and status rules

**Status:** pending

**Dependencies:** 5

**Priority:** medium

**Description:** Add deterministic freshness and status handling for managed hubs.

**Details:**

Support statuses like never, running, ok, error, and stale in the Hub Manager. Compute stale using last_extracted_at with a default threshold of 7 days. Expose status cleanly in the UI and wire refresh-stale behavior to the managed hubs data.

**Test Strategy:**

Set up hubs with different timestamps and error states and verify status badges and refresh-stale behavior.

## Subtasks

### 9.1. Define status transitions

**Status:** pending  
**Dependencies:** None  

Standardize how hub status changes during refresh lifecycle.

**Details:**

Use never before any successful run, running during refresh, ok on success, error on failure, and stale when timestamp exceeds threshold.

### 9.2. Implement stale threshold

**Status:** pending  
**Dependencies:** None  

Mark old hubs stale using last_extracted_at.

**Details:**

Default to 7 days and keep the logic simple and deterministic.

### 9.3. Wire refresh-stale flow

**Status:** pending  
**Dependencies:** None  

Make refresh-stale act only on stale managed hubs.

**Details:**

Use Hub Manager API and status logic to select stale hubs and refresh only those.
