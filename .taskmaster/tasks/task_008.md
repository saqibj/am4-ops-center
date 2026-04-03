# Task ID: 8

**Title:** Add airport badge component and search UX

**Status:** pending

**Dependencies:** 2, 5, 7

**Priority:** medium

**Description:** Upgrade the dashboard from code-first airport handling to human-readable airport search and display.

**Details:**

Create a reusable airport badge partial, add airport and aircraft search endpoints, and upgrade major pages and partials to show airport names, fullname, and country while keeping IATA visible. Prefer HTMX autocomplete over plain datalist-only UX where practical.

**Test Strategy:**

Search airports by code and name, verify richer display in Hub Explorer, My Routes, and Route Analyzer.

## Subtasks

### 8.1. Create airport badge partial

**Status:** pending  
**Dependencies:** None  

Add a reusable Jinja macro/component for airport display.

**Details:**

Create dashboard/templates/partials/airport_badge.html for compact and expanded airport rendering with IATA plus airport name/country details.

### 8.2. Add airport search endpoint

**Status:** pending  
**Dependencies:** None  

Implement /api/search/airports?q=.

**Details:**

Match IATA, ICAO, name, fullname, and country. Return useful display text for autocomplete results.

### 8.3. Add aircraft search endpoint

**Status:** pending  
**Dependencies:** None  

Implement /api/search/aircraft?q=.

**Details:**

Match shortname, name, and type. Return display-friendly result rows for autocomplete.

### 8.4. Upgrade Hub Explorer display

**Status:** pending  
**Dependencies:** None  

Show richer destination context in the hub routes table and selectors.

**Details:**

Use richer airport fields from v_best_routes and, where appropriate, use the airport badge partial.

### 8.5. Upgrade My Routes form and inventory

**Status:** pending  
**Dependencies:** None  

Use richer airport search and display in My Routes.

**Details:**

Improve hub and destination entry/search and update inventory display to show names/country, not codes only.

### 8.6. Upgrade Route Analyzer selectors and tables

**Status:** pending  
**Dependencies:** None  

Improve route-analyzer airport selection and display.

**Details:**

Replace or enhance code-only origin/destination selection using richer airport info where practical while preserving performance and HTMX simplicity.
