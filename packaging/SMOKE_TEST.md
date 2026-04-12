# Release smoke test (Windows 11 x64)

Manual checklist before treating a public release as **verified**. Complete on a **clean** Windows 11 VM (snapshot/restore between runs).

Taskmaster: **task 15** — record results here; mark the task **done** only after a full pass and sign-off.

## Run log (fill in after the test)

| Field | Value |
|--------|--------|
| **Date** | |
| **Tester** | |
| **Git tag / release** | e.g. `v0.1.1` |
| **VM image or build id** | e.g. Hyper-V / VMware snapshot name, Azure image URN, etc. |
| **Installer file** | e.g. `AM4OpsCenter-Setup-v0.1.1.exe` |
| **Installer SHA-256** | Must match release notes / published hash |
| **Outcome** | Pass / Fail / Partial |
| **Blocking issues** | Links or IDs (none if pass) |

**Sign-off:** ________________________ **Date:** __________

---

## Checklist

| Step | Pass |
|------|------|
| 1. Download `AM4OpsCenter-Setup-vX.Y.Z.exe` from the GitHub Release | ☐ |
| 2. Verify file **SHA-256** matches the release notes / published hash | ☐ |
| 3. Run installer; confirm **SmartScreen** behavior matches [README](../README.md#install-windows-11) | ☐ |
| 4. Complete wizard with defaults | ☐ |
| 5. Confirm `%LOCALAPPDATA%\Programs\AM4OpsCenter` has `AM4OpsCenter.exe`, `runtime\`, `app\`; Python 3.14 at `%LOCALAPPDATA%\Programs\Python\Python314` if bootstrapped | ☐ |
| 6. Launch from Start Menu; browser opens **`/setup`** on first run | ☐ |
| 7. Valid AM4 credentials; validation succeeds | ☐ |
| 8. Select at least one hub; extraction completes; progress UI sane | ☐ |
| 9. Dashboard shows extracted data: **Overview** or **Hub Explorer** populated; optional DB check: `v_best_routes` has rows (see [SQLite spot-check](#optional-sqlite-spot-check)) | ☐ |
| 10. Close browser; `AM4OpsCenter.exe` still running — **Stop AM4 Ops Center** shortcut ends process | ☐ |
| 11. Relaunch — goes to dashboard (setup complete), not `/setup` | ☐ |
| 12. Reboot VM; launch again — still works | ☐ |
| 13. Uninstall — choose **keep data**; `%APPDATA%\AM4OpsCenter` remains | ☐ |
| 14. Reinstall; previous DB/data still visible | ☐ |
| 15. Uninstall — choose **delete data**; `%APPDATA%\AM4OpsCenter` removed | ☐ |

If any step is **skipped**, note the step number and reason in the run log above.

---

## Optional: SQLite spot-check (`v_best_routes`)

Resolve the DB path the same way the app does (`app.paths.db_path()`), then query the view. With **sqlite3** on PATH:

```powershell
$root = "$env:LOCALAPPDATA\Programs\AM4OpsCenter"
$env:PYTHONPATH = "$root\app"
$db = & "$root\runtime\Scripts\python.exe" -c "from app.paths import db_path; print(db_path())"
sqlite3 $db "SELECT COUNT(*) FROM v_best_routes;"
```

Expect a **positive** count after a successful extraction (steps 8–9). User data dirs are described in the root [README](../README.md) and `app/paths.py` (`AM4OPS_DATA_DIR` can override).

---

## Helper commands (PowerShell)

**SHA-256 of the downloaded installer:**

```powershell
Get-FileHash -Algorithm SHA256 .\AM4OpsCenter-Setup-vX.Y.Z.exe
```

**Quick install layout:**

```powershell
Get-ChildItem "$env:LOCALAPPDATA\Programs\AM4OpsCenter" -ErrorAction SilentlyContinue
Test-Path "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe"
```

**Process check after closing the browser:**

```powershell
Get-Process AM4OpsCenter -ErrorAction SilentlyContinue
```

After **Stop AM4 Ops Center**, the process should be absent.
