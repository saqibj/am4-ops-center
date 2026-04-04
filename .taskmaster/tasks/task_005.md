# Task ID: 5

**Title:** Build Hub Manager page and APIs

**Status:** pending

**Dependencies:** 3, 4

**Priority:** high

**Description:** Add a Hub Manager page to the dashboard that lets the user manage hubs and trigger selective extraction refreshes.

**Details:**

Create a new page under My Airline, add templates and partials, and implement HTMX endpoints for hub inventory, summary, add, refresh, delete, and refresh-stale actions. The page should show status badges, timestamps, route count, best profit/day, notes, and actions for each managed hub.

**Test Strategy:**

Open the new page in the dashboard and test add valid hub, add invalid hub, refresh hub, delete hub, and refresh-stale actions.

## Subtasks

### 5.1. Add Hub Manager page route and nav link

**Status:** pending  
**Dependencies:** None  

Create the routed page and make it reachable from the left nav.

**Details:**

Add a page such as /my-hubs and place it under the My Airline section in base.html navigation.

### 5.2. Create Hub Manager templates

**Status:** pending  
**Dependencies:** None  

Add page and partial templates.

**Details:**

Create dashboard/templates/my_hubs.html, dashboard/templates/partials/hub_inventory.html, and dashboard/templates/partials/hub_summary.html with HTMX-friendly sections.

### 5.3. Add Hub Manager API endpoints

**Status:** pending  
**Dependencies:** None  

Implement inventory, summary, add, refresh, delete, and refresh-stale APIs.

**Details:**

Add GET /api/hubs/inventory, GET /api/hubs/summary, POST /api/hubs/add, POST /api/hubs/refresh, POST /api/hubs/delete, and POST /api/hubs/refresh-stale.

### 5.4. Support one and many hub add flows

**Status:** pending  
**Dependencies:** None  

Allow one-hub and comma-separated multi-hub add in the GUI.

**Details:**

The add form should accept a single IATA or a comma-separated list and create my_hubs rows accordingly with validation feedback.

### 5.5. Add per-row and bulk refresh actions

**Status:** pending  
**Dependencies:** None  

Support row refresh and stale refresh from the GUI.

**Details:**

Include actions to refresh one hub, refresh selected hubs if practical, and refresh stale hubs only.

### 5.6. Add safe delete behavior

**Status:** pending  
**Dependencies:** None  

Allow removing a managed hub, with optional extracted-data cleanup.

**Details:**

Deleting a managed hub should not affect unrelated hubs. If extracted data removal is implemented, it should only remove selected origin hub data.
