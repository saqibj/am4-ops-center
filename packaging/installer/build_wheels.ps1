<#
.SYNOPSIS
    Downloads all pip dependencies for am4-ops-center into packaging/installer/wheels/
    so the Inno Setup installer can pip install offline on the user's machine.

.DESCRIPTION
    Run before compiling the installer with iscc. CI also runs this fresh on every build.

    Behavior:
      1. Clears packaging/installer/wheels/
      2. Downloads all requirements.txt deps as Windows x64 cp314 wheels
      3. Downloads the pip wheel itself (for the installer's `pip install --upgrade pip` step)
      4. Copies the am4 wheel from either:
           - a -Am4WheelPath explicitly provided, OR
           - the GitHub Release asset for the current tag (via gh CLI), OR
           - the latest successful build-am4-wheel workflow artifact
      5. Fails if ANY sdist (.tar.gz, .zip) slipped in — the installer must not
         compile anything on user machines
      6. Writes MANIFEST.txt with sha256 for every wheel

.PARAMETER Am4WheelPath
    Optional explicit path to the prebuilt am4 wheel. If not provided, the script
    attempts to fetch it via gh CLI from the current repo's releases or workflow runs.

.PARAMETER PythonVersion
    Python version tag for pip download. Default: 3.14

.PARAMETER SkipAm4
    Skip the am4 wheel fetch entirely. Useful for local iteration when you've
    already staged it manually. The installer build will fail later if am4 is
    missing, so only use this during development.

.EXAMPLE
    .\build_wheels.ps1
    # Auto-fetches am4 wheel from GitHub

.EXAMPLE
    .\build_wheels.ps1 -Am4WheelPath "C:\temp\am4-0.1.0-cp314-cp314-win_amd64.whl"
    # Uses a local am4 wheel

.EXAMPLE
    .\build_wheels.ps1 -SkipAm4
    # Dev-only: skip am4, test rest of flow
#>

[CmdletBinding()]
param(
    [string]$Am4WheelPath,
    [string]$PythonVersion = '3.14',
    [switch]$SkipAm4
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# ---------------------------------------------------------------------------
# Resolve paths: this script lives at packaging/installer/build_wheels.ps1
# ---------------------------------------------------------------------------
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallerDir = $ScriptDir
$RepoRoot     = Resolve-Path (Join-Path $ScriptDir '..\..')
$WheelsDir    = Join-Path $InstallerDir 'wheels'
$RequirementsPath = Join-Path $RepoRoot 'requirements.txt'

Write-Host "============================================================"
Write-Host "  am4-ops-center offline wheel builder"
Write-Host "============================================================"
Write-Host "Repo root    : $RepoRoot"
Write-Host "Wheels dir   : $WheelsDir"
Write-Host "Requirements : $RequirementsPath"
Write-Host "Python ver   : $PythonVersion"
Write-Host ""

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------
if (-not (Test-Path $RequirementsPath)) {
    throw "requirements.txt not found at $RequirementsPath"
}

try {
    $pyVer = (python --version) 2>&1
    Write-Host "Using local pip from: $pyVer"
} catch {
    throw "Python not found on PATH. Install Python and try again."
}

# ---------------------------------------------------------------------------
# Step 1: Clean and recreate the wheels directory
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[1/6] Clearing $WheelsDir..."
if (Test-Path $WheelsDir) {
    Remove-Item -Recurse -Force $WheelsDir
}
New-Item -ItemType Directory -Path $WheelsDir | Out-Null

# ---------------------------------------------------------------------------
# Step 2: Download app requirements as wheels
# am4 is installed from the prebuilt wheel in step 4 — skip VCS lines here
# because pip download --only-binary cannot satisfy git+https://...
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/6] Downloading requirements.txt dependencies (excluding am4 VCS pin)..."
$tempReq = Join-Path $env:TEMP "am4ops-pip-download-requirements.txt"
Get-Content $RequirementsPath | Where-Object { $_ -notmatch '^\s*am4\s' } | Set-Content -Encoding utf8 $tempReq
$abi = "cp$($PythonVersion -replace '\.','')"
$pipArgs = @(
    '-m', 'pip', 'download',
    '--dest', $WheelsDir,
    '--python-version', $PythonVersion,
    '--platform', 'win_amd64',
    '--implementation', 'cp',
    '--abi', $abi,
    '--only-binary=:all:',
    '-r', $tempReq
)
Write-Host "pip $($pipArgs -join ' ')"
& python @pipArgs
if ($LASTEXITCODE -ne 0) {
    throw "pip download failed for requirements.txt. Check that every dependency has a Windows x64 $abi wheel on PyPI."
}

# ---------------------------------------------------------------------------
# Step 3: Download pip itself
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[3/6] Downloading pip wheel..."
& python -m pip download --dest $WheelsDir --only-binary=:all: pip
if ($LASTEXITCODE -ne 0) {
    throw "pip download failed for pip itself"
}

# ---------------------------------------------------------------------------
# Step 4: Acquire the am4 wheel
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[4/6] Acquiring am4 wheel..."

if ($SkipAm4) {
    Write-Warning "  -SkipAm4 specified; am4 wheel will NOT be staged. Installer build will fail."
}
elseif ($Am4WheelPath) {
    if (-not (Test-Path $Am4WheelPath)) {
        throw "Am4WheelPath does not exist: $Am4WheelPath"
    }
    Write-Host "  Copying from: $Am4WheelPath"
    Copy-Item $Am4WheelPath -Destination $WheelsDir
}
else {
    $ghAvailable = $null -ne (Get-Command gh -ErrorAction SilentlyContinue)
    if (-not $ghAvailable) {
        throw @"
Cannot auto-fetch am4 wheel: gh CLI not installed.
Either:
  1. Install gh (https://cli.github.com/) and authenticate with 'gh auth login', OR
  2. Pass -Am4WheelPath pointing to a locally built wheel, OR
  3. Download the am4 wheel from GitHub Releases manually and drop it into
     $WheelsDir, then rerun with -SkipAm4
"@
    }

    Write-Host "  Fetching latest am4-wheel artifact via gh CLI..."
    Push-Location $RepoRoot
    try {
        $runIdJson = gh run list --workflow 'build-am4-wheel.yml' --status success --limit 1 --json databaseId
        if ($LASTEXITCODE -ne 0 -or -not $runIdJson) {
            throw "No successful build-am4-wheel workflow run found. Run it once via 'gh workflow run build-am4-wheel.yml' first."
        }
        $runId = ($runIdJson | ConvertFrom-Json)[0].databaseId
        Write-Host "  Found workflow run: $runId"

        $tempDl = Join-Path $env:TEMP "am4-wheel-$runId"
        if (Test-Path $tempDl) { Remove-Item -Recurse -Force $tempDl }
        gh run download $runId --name am4-wheel --dir $tempDl
        if ($LASTEXITCODE -ne 0) {
            throw "gh run download failed for run $runId"
        }

        $downloadedWheel = Get-ChildItem $tempDl\*.whl | Select-Object -First 1
        if (-not $downloadedWheel) {
            throw "No .whl file found in downloaded am4-wheel artifact"
        }
        Copy-Item $downloadedWheel.FullName -Destination $WheelsDir
        Write-Host "  Staged: $($downloadedWheel.Name)"
    }
    finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# Step 5: Sanity check — no sdists allowed
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[5/6] Verifying no source distributions snuck in..."
$sdists = @(Get-ChildItem $WheelsDir -Include *.tar.gz, *.zip -File -ErrorAction SilentlyContinue)
if ($sdists.Count -gt 0) {
    Write-Host ""
    Write-Host "ERROR: Source distributions found in wheels/:" -ForegroundColor Red
    $sdists | ForEach-Object { Write-Host "  $($_.Name)" -ForegroundColor Red }
    throw "Sdist present in wheels dir"
}

$wheels = @(Get-ChildItem $WheelsDir -Filter *.whl)
if ($wheels.Count -eq 0) {
    throw "No wheels in $WheelsDir after download steps"
}
Write-Host "  OK: $($wheels.Count) wheels, no sdists"

if (-not $SkipAm4) {
    $am4Wheels = @($wheels | Where-Object { $_.Name -like 'am4-*' })
    if ($am4Wheels.Count -eq 0) {
        Write-Warning "No am4-*.whl in wheels dir — installer will fail at the am4 install step"
    }
}

# ---------------------------------------------------------------------------
# Step 6: Write MANIFEST.txt with sha256 for every wheel
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[6/6] Writing MANIFEST.txt..."
$manifestPath = Join-Path $WheelsDir 'MANIFEST.txt'
$lines = @(
    "# am4-ops-center offline wheel manifest",
    "# Generated: $(Get-Date -Format 'o')",
    "# Python: $PythonVersion / win_amd64",
    "# Total wheels: $($wheels.Count)",
    ""
)
foreach ($w in ($wheels | Sort-Object Name)) {
    $hash = (Get-FileHash -Algorithm SHA256 $w.FullName).Hash.ToLowerInvariant()
    $size = $w.Length
    $lines += "{0}  {1}  {2} bytes" -f $hash, $w.Name, $size
}
$lines | Out-File -FilePath $manifestPath -Encoding utf8

Write-Host ""
Write-Host "============================================================"
Write-Host "  Done."
Write-Host "  Wheels   : $($wheels.Count)"
Write-Host "  Location : $WheelsDir"
Write-Host "  Manifest : $manifestPath"
Write-Host "============================================================"
