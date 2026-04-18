DROP INDEX IF EXISTS idx_ra_origin_extracted;
CREATE INDEX IF NOT EXISTS idx_ra_origin_extracted
ON route_aircraft (origin_id, extracted_at)
WHERE is_valid = 1;
