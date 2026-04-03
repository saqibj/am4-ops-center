# Task ID: 6

**Title:** Implement fleet merge-by-default and buy-sell UX

**Status:** pending

**Dependencies:** 4

**Priority:** high

**Description:** Make my_fleet additive by default in both CLI and GUI and add row-level buy/sell actions with assigned/free counts.

**Details:**

Update commands/airline.py and dashboard/routes/api_routes.py so duplicate aircraft types increment quantity by default instead of replacing it. Add buy and sell endpoints, and upgrade the fleet table to show owned, assigned, free, type, cost each, total value, and actions.

**Test Strategy:**

Add new aircraft, add duplicate aircraft, buy more, sell some, sell all, and verify summary cards update correctly.

## Subtasks

### 6.1. Switch fleet import default to merge

**Status:** pending  
**Dependencies:** None  

Change CLI import behavior from overwrite to additive by default.

**Details:**

Existing quantity should increment by imported count in merge mode, with explicit replace mode still supported.

### 6.2. Switch GUI fleet add default to additive

**Status:** pending  
**Dependencies:** None  

Change /api/fleet/add behavior.

**Details:**

If the aircraft already exists in my_fleet, increment quantity instead of overwriting it. Return clear flash messaging.

### 6.3. Add row-level buy endpoint

**Status:** pending  
**Dependencies:** None  

Implement /api/fleet/{id}/buy.

**Details:**

Support an add_count input and increment quantity safely.

### 6.4. Add row-level sell endpoint

**Status:** pending  
**Dependencies:** None  

Implement /api/fleet/{id}/sell.

**Details:**

Support sell_count input, decrement safely, and remove row if quantity becomes zero after confirmation.

### 6.5. Add assigned and free counts to fleet inventory

**Status:** pending  
**Dependencies:** None  

Compute assignment-aware inventory metrics.

**Details:**

Compute assigned aircraft counts from my_routes and show free = owned - assigned in the fleet table and summary where appropriate.

### 6.6. Upgrade fleet inventory columns

**Status:** pending  
**Dependencies:** None  

Add richer operational columns to the UI.

**Details:**

Show shortname, name, type, owned, assigned, free, cost each, total value, notes, and actions. Preserve current basic behavior where practical.
