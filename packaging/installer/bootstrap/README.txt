Bundled Python.org Windows x64 embeddable installer (optional bootstrap)

Files:
  PYTHON_VERSION.txt           — full version, e.g. 3.14.3 (single line, trimmed)
  PYTHON_INSTALLER_SHA256.txt  — lowercase hex SHA-256 of python-<ver>-amd64.exe
  python-installer.exe         — not in git; CI downloads before iscc (see build-installer workflow)

Bump checklist:
  1. Set PYTHON_VERSION.txt to the new full version (must match python.org path segment).
  2. Download https://www.python.org/ftp/python/<ver>/python-<ver>-amd64.exe
  3. Compute SHA-256 (PowerShell: Get-FileHash -Algorithm SHA256 .\python-*-amd64.exe)
  4. Put the lowercase hex hash in PYTHON_INSTALLER_SHA256.txt
  5. If the install directory for 3.14 changes, update PythonTargetDir / PythonVersion in am4opscenter.iss

Conda / Store-only Python: the installer may still bundle python.org if the PythonCore registry
keys and `py -3.14` launcher do not resolve to a usable python.exe.
