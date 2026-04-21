-- Task 2: Buy Next Global and Task 3: Homepage optimizations

-- Speed up JOIN with my_routes_collapsed in Buy Next Global
CREATE INDEX IF NOT EXISTS idx_my_routes_od ON my_routes(origin_id, dest_id);

-- Speed up JOIN with my_fleet to exclude owned aircraft
CREATE INDEX IF NOT EXISTS idx_my_fleet_ac_qty ON my_fleet(aircraft_id) WHERE quantity > 0;

-- Improve covering index for Buy Next Global by adding aircraft_id
-- This helps when joining with aircraft table to filter by cost/type
DROP INDEX IF EXISTS idx_ra_valid_profit;
CREATE INDEX idx_ra_valid_profit ON route_aircraft(is_valid, aircraft_id, profit_per_ac_day DESC);

-- Speed up Homepage Top Hubs aggregation
CREATE INDEX IF NOT EXISTS idx_ra_origin_valid_profit_id ON route_aircraft(origin_id, is_valid, profit_per_ac_day DESC);

-- Speed up last_extract query
CREATE INDEX IF NOT EXISTS idx_ra_valid_extracted ON route_aircraft(is_valid, extracted_at DESC);

-- Speed up filtering by aircraft type/cost followed by profit sort
CREATE INDEX IF NOT EXISTS idx_ra_ac_valid_profit ON route_aircraft(aircraft_id, is_valid, profit_per_ac_day DESC);
