# Phase 2 Performance Baseline

**Captured:** 2026-04-07 17:38 UTC  
**Machine:** Windows, Python 3.12, SQLite (no WAL, no pragmas yet)  
**Method:** `?debug=1` profiling middleware, cold = first hit after fresh `uvicorn` restart  

| Page | Cold total (ms) | Cold DB (ms) | Queries | Warm avg total (ms) | Warm avg DB (ms) | Response (bytes) |
|------|----------------:|-------------:|--------:|--------------------:|-----------------:|-----------------:|
| / (index) | 43418.92 | 10549.25 | 5 | 18209.0 | 9730.31 | 16301 |
| /buy-next?hub=LAX | 31087.38 | 11226.08 | 6 | 34106.8 | 12369.77 | 13384 |
| /my-fleet | 23554.69 | 9332.17 | 3 | 16701.4 | 6719.47 | 36033 |
| /my-routes | 19836.31 | 5996.96 | 4 | 22860.4 | 7304.45 | 292097 |
| /hub-explorer | 42569.27 | 17158.07 | 3 | 18470.6 | 8447.03 | 10614 |
| /contributions | 20345.22 | 9603.87 | 3 | 19854.9 | 8955.52 | 8797 |

## Notes

- Cold timings include Python module import, template compilation, and SQLite page cache warming.
- Warm timings are the average of 3 subsequent hits.
- DB time only counts `conn.execute()` calls; connection open overhead is in the total but not in DB time.
- Response bytes include the `<!-- perf: ... -->` debug trailer (~150 bytes).
- These numbers serve as the before-optimization reference for tasks 2-6.
