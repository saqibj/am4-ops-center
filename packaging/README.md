# Packaging Layout

This directory contains all packaging artifacts used to build and distribute AM4 Ops Center.

## Structure

- `installer/` - Windows installer assets and Inno Setup script.
  - `am4opscenter.iss` - Inno Setup definition.
  - `assets/` - Installer static assets (icons, license text, banner images).
  - `bootstrap/` - Bootstrap scripts used during installation.
  - `wheels/` - Offline Python wheel cache bundled with installer builds.
- `launcher/` - Standalone launcher entrypoint and PyInstaller config.
  - `am4opscenter_launcher.py` - Launcher executable entry script.
  - `launcher.spec` - PyInstaller spec for launcher build.
  - `icon.ico` - Launcher icon.
- `ci/` - CI workflows that build wheel, installer, and release artifacts.
  - `build_am4_wheel.yml`
  - `build_installer.yml`
  - `release.yml`

## Notes

- Keep build outputs out of source control (`dist/`, bundled wheels, and bootstrap artifacts are ignored).
- Placeholder files are intentionally lightweight and will be implemented in later tasks.
- Runtime writable data (database, config, logs) uses platformdirs by default and can be overridden with `AM4OPS_DATA_DIR` for local/dev setups.
- Setup wizard credentials are stored locally at `config_dir()/credentials.json` using machine-derived `Fernet` encryption. This protects local-at-rest data but is not a remote secrets manager.

## AM4 Wheel CI

- Canonical wheel build workflow source is maintained in `packaging/installer/build-am4-wheel.yml`.
- GitHub entrypoint is `.github/workflows/build-am4-wheel.yml` (dispatch/tag trigger), which calls `.github/workflows/_build-am4-wheel-reusable.yml`.
- MSYS2 toolchain packages currently installed by CI:
  - `mingw-w64-x86_64-gcc`
  - `mingw-w64-x86_64-gcc-libs`
  - `mingw-w64-x86_64-cmake`
  - `mingw-w64-x86_64-ninja`
  - `mingw-w64-x86_64-make`
  - `git`
- AM4 source is pinned with repository variable `AM4_COMMIT_SHA` (required).
- To bump AM4:
  1. Update repository variable `AM4_COMMIT_SHA`.
  2. Run workflow manually.
  3. Confirm smoke test passes and artifact wheel imports cleanly.

## Python.org bootstrap (installer)

- Pinned version: `packaging/installer/bootstrap/PYTHON_VERSION.txt` (e.g. `3.14.3`).
- SHA-256 of `python-<version>-amd64.exe`: `packaging/installer/bootstrap/PYTHON_INSTALLER_SHA256.txt` (lowercase hex).
- The actual `python-installer.exe` is **not** committed; CI downloads it before `iscc`.
- Bump procedure: see `packaging/installer/bootstrap/README.txt`.

## Offline wheels (`build_wheels.ps1`)

- Script: `packaging/installer/build_wheels.ps1` (run from repo root or any cwd; paths are resolved from the script location).
- Populates `packaging/installer/wheels/` and writes `MANIFEST.txt`.
- `am4` is copied from `-Am4WheelPath` or fetched via `gh` from the latest successful `build-am4-wheel` run; other deps come from root `requirements.txt` (the `am4` VCS line is skipped for `pip download`).

## Installer CI

- Workflow: `.github/workflows/build-installer.yml`.
- Triggers: `workflow_dispatch` and `workflow_call` (not tag push — avoids duplicate jobs).
- First job runs the reusable AM4 wheel build; the second stages `dist/app`, runs PyInstaller, `build_wheels.ps1`, downloads the pinned Python installer, and runs Inno Setup.
- Artifact name: `installer` (the `AM4OpsCenter-Setup-*.exe` under `packaging/installer/Output/`).

## Release (tags)

- Workflow: `.github/workflows/release.yml`.
- Triggers: push tags matching **`v*.*.*`** (e.g. `v1.0.0`, `v0.2.3-rc1`).
- Calls `build-installer.yml` once, then publishes a **GitHub Release** (not draft) with the **`.whl`** and **`.exe`** assets and generated notes. Body links to root **`CHANGELOG.md`**.
- **Tag protection (recommended):** In GitHub → Settings → Rules → Rulesets, restrict who can create matching tags, or document team process: tag only from `main` after CI is green. This is not enforced in-repo.

## Uninstall (installed app)

- Windows **Settings → Apps → AM4 Ops Center → Uninstall**.
- The uninstaller removes the install directory (including the bundled venv). It **prompts** whether to delete **`%APPDATA%\AM4OpsCenter`** (database, encrypted credentials, logs); default is **keep** for reinstalls.

## Legacy placeholder

- `packaging/ci/release.yml` is not a GitHub Actions path; release automation is **`.github/workflows/release.yml`** only.
