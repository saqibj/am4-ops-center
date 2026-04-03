# Task ID: 10

**Title:** Clean up README and dependency consistency

**Status:** pending

**Dependencies:** 5, 6, 7, 8, 9

**Priority:** medium

**Description:** Make docs and packaging reflect the real app and its new behavior.

**Details:**

Update README.md, help text, and dependency references so the documented pages and commands match the real routed UI and CLI. Remove or correct Buy Next references unless implemented. Clarify full rebuild versus hub refresh and merge versus replace semantics for fleet and routes import. Reconcile requirements.txt and pyproject.toml dependency source differences or explicitly document why they differ.

**Test Strategy:**

Read README end-to-end and run documented commands to confirm they match real behavior.

## Subtasks

### 10.1. Fix dashboard page list and feature claims

**Status:** pending  
**Dependencies:** None  

Align README with actual routed UI.

**Details:**

Remove false Buy Next page claims unless the page is actually implemented. Add Hub Manager if implemented. Ensure page count and descriptions are accurate.

### 10.2. Document extraction modes

**Status:** pending  
**Dependencies:** None  

Clarify full rebuild and hub refresh behavior.

**Details:**

Explain when to use full rebuild versus selected-hub refresh, including command examples.

### 10.3. Document import semantics

**Status:** pending  
**Dependencies:** None  

Clarify merge versus replace for fleet and route import.

**Details:**

Explain that merge is default and replace is explicit, with CLI examples and expected behavior.

### 10.4. Resolve or explain dependency source mismatch

**Status:** pending  
**Dependencies:** None  

Make requirements and pyproject consistent enough for users.

**Details:**

Either align the AM4 dependency source across requirements.txt and pyproject.toml or explicitly explain why they differ and which path users should trust.
