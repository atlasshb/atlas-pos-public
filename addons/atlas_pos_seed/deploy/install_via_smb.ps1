<#
=====================================================================
 install_via_smb.ps1  --  Deploy Option A
=====================================================================
 Copies the "atlas_pos_seed" module folder onto the live Odoo
 Windows host over SMB (\\192.0.2.10\...), into the Odoo addons
 path, then tells you to Update Apps List + Install in the Odoo UI.

 SAFETY:
   - Additive copy only. Does NOT touch the database, accounting,
     taxes, or any existing module. Just places files.
   - NO secrets are hardcoded. Credentials (if the share needs them)
     are PROMPTED at runtime via Get-Credential, never stored.

 BEFORE YOU RUN: fill in the TODO placeholders in the CONFIG block.
 Run from a Windows machine that can reach \\192.0.2.10 :
     powershell -ExecutionPolicy Bypass -File .\install_via_smb.ps1
=====================================================================
#>

[CmdletBinding()]
param(
    # Override any of the CONFIG values from the command line if you prefer.
    [string] $RemoteAddonsShare,
    [switch] $UseCredentials,   # pass -UseCredentials if the share requires a Windows login
    [switch] $WhatIfCopy        # pass -WhatIfCopy to preview without copying
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# =====================================================================
#  CONFIG -- EDIT THESE  (TODO placeholders)
# =====================================================================

# (1) TODO: The UNC path to the Odoo *addons* directory on the host.
#     This must be the folder that appears in the Odoo addons_path
#     (check odoo.conf on the server). Examples (pick the real one):
#        \\192.0.2.10\odoo-addons
#        \\192.0.2.10\C$\Program Files\Odoo 19.0\server\odoo\addons
#        \\192.0.2.10\odoo\custom-addons
$DefaultRemoteAddonsShare = '\\192.0.2.10\TODO-share-name\TODO-addons-subfolder'

# (2) TODO (optional): If the SMB share needs a specific Windows account,
#     run this script with  -UseCredentials  and you will be PROMPTED.
#     Do NOT write a username/password here.
#     Example domain\user you will type at the prompt: 192.0.2.10\Administrator

# (3) The Odoo connection info (used only for the printed instructions at the end).
$OdooUrl    = 'http://192.0.2.10:8069'
$OdooDb     = 'venue_b'
$ModuleName = 'atlas_pos_seed'

# =====================================================================
#  Resolve paths
# =====================================================================

if ([string]::IsNullOrWhiteSpace($RemoteAddonsShare)) {
    $RemoteAddonsShare = $DefaultRemoteAddonsShare
}

# The module folder is the PARENT of this /deploy folder.
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ModuleDir   = Split-Path -Parent $ScriptDir          # ...\atlas_pos_seed
$ModuleLeaf  = Split-Path -Leaf   $ModuleDir          # "atlas_pos_seed"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " Venue B POS  --  SMB deploy (Option A)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host (" Local module folder : {0}" -f $ModuleDir)
Write-Host (" Module name         : {0}" -f $ModuleLeaf)
Write-Host (" Remote addons share : {0}" -f $RemoteAddonsShare)
Write-Host ""

# --- Guard: did someone forget to edit the TODO placeholder? ---
if ($RemoteAddonsShare -like '*TODO*') {
    Write-Host "ERROR: The remote addons share still contains a TODO placeholder." -ForegroundColor Red
    Write-Host "       Edit the CONFIG block in this script (or pass -RemoteAddonsShare)." -ForegroundColor Red
    Write-Host "       Set it to the real \\192.0.2.10\... addons path from odoo.conf." -ForegroundColor Red
    exit 1
}

# --- Guard: local module folder must look like an Odoo module ---
if ($ModuleLeaf -ne $ModuleName) {
    Write-Host ("WARNING: Module folder is named '{0}', expected '{1}'." -f $ModuleLeaf, $ModuleName) -ForegroundColor Yellow
}
$manifest = Join-Path $ModuleDir '__manifest__.py'
if (-not (Test-Path $manifest)) {
    Write-Host "WARNING: No __manifest__.py found in the module folder." -ForegroundColor Yellow
    Write-Host ("         Looked at: {0}" -f $manifest) -ForegroundColor Yellow
    Write-Host "         Copy will still proceed, but Odoo won't see it as a module without a manifest." -ForegroundColor Yellow
}

# =====================================================================
#  Optionally map the share with credentials (prompted, never stored)
# =====================================================================

# We connect to the SERVER ROOT of the share so we can authenticate once.
$bs = [string][char]92                                   # a single backslash
$parts = $RemoteAddonsShare.TrimStart($bs[0]) -split ([regex]::Escape($bs))
$parts = $parts | Where-Object { $_ } | Select-Object -First 2
$shareRoot = $bs + $bs + ($parts -join $bs)              # e.g. \\192.0.2.10\share-name

$mappedDrive = $null
if ($UseCredentials) {
    Write-Host ("This share may require a Windows login: {0}" -f $shareRoot) -ForegroundColor Yellow
    Write-Host "You will be prompted. Nothing is saved to disk." -ForegroundColor Yellow
    $cred = Get-Credential -Message ("Credentials for {0}" -f $shareRoot)

    # Use a temporary PSDrive so the credential is held only for this session.
    try {
        New-PSDrive -Name 'Venue BSMB' -PSProvider FileSystem -Root $shareRoot -Credential $cred -ErrorAction Stop | Out-Null
        $mappedDrive = 'Venue BSMB'
        Write-Host "Authenticated to the share (temporary session drive)." -ForegroundColor Green
    }
    catch {
        Write-Host ("ERROR: Could not connect to {0}: {1}" -f $shareRoot, $_.Exception.Message) -ForegroundColor Red
        exit 1
    }
}

# =====================================================================
#  Verify reachability + copy
# =====================================================================

try {
    if (-not (Test-Path -LiteralPath $RemoteAddonsShare)) {
        Write-Host ("ERROR: Remote addons path is not reachable: {0}" -f $RemoteAddonsShare) -ForegroundColor Red
        Write-Host "       Checklist:" -ForegroundColor Red
        Write-Host "         - Is the path correct (matches odoo.conf addons_path)?" -ForegroundColor Red
        Write-Host "         - Is file sharing enabled on the host and reachable from here?" -ForegroundColor Red
        Write-Host "         - Does the share need credentials?  Re-run with  -UseCredentials" -ForegroundColor Red
        exit 1
    }

    $destination = Join-Path $RemoteAddonsShare $ModuleLeaf
    Write-Host ("Copying module -> {0}" -f $destination) -ForegroundColor Cyan

    # robocopy: mirror the module folder. /MIR keeps the destination clean on re-deploy
    # (idempotent: re-running gives the same result). Excludes VCS/cache junk.
    $roboArgs = @(
        ("`"{0}`"" -f $ModuleDir),
        ("`"{0}`"" -f $destination),
        '/MIR',
        '/XD', '.git', '__pycache__', '.idea', '.vscode',
        '/XF', '*.pyc', '*.pyo',
        '/R:2', '/W:2',
        '/NFL', '/NDL', '/NP'
    )
    if ($WhatIfCopy) { $roboArgs += '/L' }   # /L = list only, no copy

    $robocopy = Join-Path $env:SystemRoot 'System32\robocopy.exe'
    & $robocopy @roboArgs | Out-Host
    $rc = $LASTEXITCODE

    # robocopy exit codes: 0..7 are success (8+ is an actual failure).
    if ($rc -ge 8) {
        Write-Host ("ERROR: robocopy failed with exit code {0}." -f $rc) -ForegroundColor Red
        exit $rc
    }
    if ($WhatIfCopy) {
        Write-Host "Preview only (-WhatIfCopy) -- nothing was copied." -ForegroundColor Yellow
    } else {
        Write-Host "Module files copied successfully." -ForegroundColor Green
    }
}
finally {
    if ($mappedDrive) {
        Remove-PSDrive -Name $mappedDrive -ErrorAction SilentlyContinue
    }
}

# =====================================================================
#  Next steps (manual, in the Odoo UI)
# =====================================================================

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host " FILES ARE IN PLACE. Now finish in the Odoo web UI:" -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Green
Write-Host (" 1. RESTART the Odoo service on the host so it rescans addons.") -ForegroundColor White
Write-Host ("    (Windows: services.msc -> restart the Odoo 19 service.)") -ForegroundColor White
Write-Host (" 2. Open {0}  and log in as admin." -f $OdooUrl) -ForegroundColor White
Write-Host (" 3. Enable Developer Mode (Settings -> Developer Tools -> Activate).") -ForegroundColor White
Write-Host (" 4. Apps -> (top menu) Update Apps List -> Update.") -ForegroundColor White
Write-Host ("    5. Search for the module {0} -> Install." -f $ModuleName) -ForegroundColor White
Write-Host (" 6. DB in use: {0}" -f $OdooDb) -ForegroundColor White
Write-Host ""
Write-Host " Then run the POST-DEPLOY SMOKE TEST in README_DEPLOY.md:" -ForegroundColor Cyan
Write-Host "   ring up a gala dress + an alteration, pay via the manual" -ForegroundColor Cyan
Write-Host "   Pinnen / Worldline kaart method, and print the receipt." -ForegroundColor Cyan
Write-Host ""
Write-Host " REMINDER (manual admin steps, see README): confirm l10n_nl is installed" -ForegroundColor Yellow
Write-Host " and the company default sales tax is 21% BTW. Do NOT install l10n_tr." -ForegroundColor Yellow
