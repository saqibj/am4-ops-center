-- 60-second persisted undo for route adds (Task 8). Safe to re-run.
CREATE TABLE IF NOT EXISTS route_add_undos (
  token TEXT PRIMARY KEY,
  route_id INTEGER NOT NULL,
  fleet_id INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_route_add_undos_expires ON route_add_undos(expires_at);
