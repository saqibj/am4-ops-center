# Task ID: 2

**Title:** Add managed hubs schema and richer airport route views

**Status:** pending

**Dependencies:** 1

**Priority:** high

**Description:** Extend the database schema to support managed hubs and richer airport metadata in existing route views.

**Details:**

Update database/schema.py to add my_hubs, an index on airport_id, a v_my_hubs view, and richer airport fields in v_my_routes and v_best_routes. Preserve all existing columns currently consumed by templates and APIs.

**Test Strategy:**

Start dashboard after schema changes and verify all existing pages still load without SQL or template errors.

## Subtasks

### 2.1. Add my_hubs table

**Status:** pending  
**Dependencies:** None  

Create a managed hubs table with extraction state.

**Details:**

Add columns: id, airport_id unique, notes, is_active, created_at, updated_at, last_extracted_at, last_extract_status, last_extract_error. Add foreign key to airports(id).

### 2.2. Add idx_my_hubs_airport

**Status:** pending  
**Dependencies:** None  

Add supporting index for managed hubs lookup.

**Details:**

Create an index on my_hubs(airport_id) to keep lookup and join performance predictable.

### 2.3. Create v_my_hubs view

**Status:** pending  
**Dependencies:** None  

Create a dashboard-ready managed hubs view.

**Details:**

Join my_hubs to airports and expose id, airport_id, iata, icao, name, fullname, country, continent, market, hub_cost, notes, is_active, last_extracted_at, last_extract_status, last_extract_error.

### 2.4. Upgrade v_my_routes with richer airport fields

**Status:** pending  
**Dependencies:** None  

Add airport display metadata to the current my_routes view.

**Details:**

Add hub_name, hub_country, dest_name, dest_fullname, dest_country without removing existing hub, destination, aircraft, and other current columns.

### 2.5. Upgrade v_best_routes with richer airport fields

**Status:** pending  
**Dependencies:** None  

Add airport display metadata to the best-routes view.

**Details:**

Add hub_name, hub_country, dest_name, dest_fullname, dest_country while preserving current fields used by existing pages.
