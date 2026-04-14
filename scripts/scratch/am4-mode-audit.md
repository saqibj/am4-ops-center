# AM4 game_mode / realism audit (2026-04-14)

Call sites that affect route profit / contribution via the `am4` library:

| Location | Notes |
|----------|--------|
| `extractors/routes.py:35` | `build_am4_user` → `User.Default(realism=…)`, `user.game_mode` — **primary** profit path for extraction |
| `extractors/routes.py:125` | `RoutesSearch(..., user=user)` uses built user |
| `extractors/routes.py:322` | `Airport.search` — airport master only, no User |
| `extractors/aircraft.py` | `Aircraft.search` — aircraft master, no User |
| `extractors/airports.py` | `Airport.search` — airport master, no User |
| `dashboard/routes/api/hubs.py` | `am4.utils.db.init` only |
| `dashboard/routes/setup.py`, `database/setup_flow.py` | `init` only |
| `main.py:92` | CLI `extract` uses `am4.utils.db.init` |

**Conclusion:** Thread `read_game_mode(conn)` / `core.game_mode.is_realism` through `build_am4_user` whenever a DB connection is available; keep CLI-only paths on `UserConfig.game_mode`.
