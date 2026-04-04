# Task ID: 4

**Title:** Add CLI parity for extract modes and import merge semantics

**Status:** pending

**Dependencies:** 3

**Priority:** high

**Description:** Expose explicit CLI options for full rebuild versus hub refresh and for merge versus replace import behavior.

**Details:**

Update main.py and command handling so extract supports explicit replace and refresh semantics. Update fleet import and routes import so merge is the default and replace is explicit. Keep existing simple workflows usable where practical and update help text immediately when semantics change.

**Test Strategy:**

Run help commands and representative CLI examples. Confirm help text matches real behavior.

## Subtasks

### 4.1. Add extract mode flags

**Status:** pending  
**Dependencies:** None  

Expose full rebuild and hub refresh semantics in CLI.

**Details:**

Support commands equivalent to full replace/rebuild and selected hub refresh/append with explicit user-facing flags.

### 4.2. Add fleet import merge and replace flags

**Status:** pending  
**Dependencies:** None  

Make merge the default for fleet imports.

**Details:**

Support --merge and --replace, default to merge, and ensure help text reflects it.

### 4.3. Add routes import merge and replace flags

**Status:** pending  
**Dependencies:** None  

Make merge the default for route imports.

**Details:**

Support --merge and --replace, default to merge, and ensure help text reflects it.
