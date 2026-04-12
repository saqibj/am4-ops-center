# Release smoke test (Windows 11 x64)

Manual checklist before treating a public release as **verified**. Complete on a **clean** Windows 11 VM (snapshot/restore between runs).

**Record here after the run:** date, tester, VM image or build id, **installer SHA-256**, git tag, and any skipped steps + reason.

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
| 9. Dashboard shows expected data (e.g. routes / views populated) | ☐ |
| 10. Close browser; `AM4OpsCenter.exe` still running — **Stop AM4 Ops Center** shortcut ends process | ☐ |
| 11. Relaunch — goes to dashboard (setup complete), not `/setup` | ☐ |
| 12. Reboot VM; launch again — still works | ☐ |
| 13. Uninstall — choose **keep data**; `%APPDATA%\AM4OpsCenter` remains | ☐ |
| 14. Reinstall; previous DB/data still visible | ☐ |
| 15. Uninstall — choose **delete data**; `%APPDATA%\AM4OpsCenter` removed | ☐ |

**Sign-off:** ________________________ **Date:** __________
