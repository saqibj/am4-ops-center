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
