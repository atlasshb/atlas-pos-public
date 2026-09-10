#requires -Version 5.1
<#
  Atlas POS-Ops — one-shot terminal onboarding.

  Drop this folder onto a new POS terminal (via MeshCentral file transfer or
  USB) and run as Administrator. It:
    1. Verifies Tailscale is up + reports the tailnet IP
    2. Calls pos-hub /api/enroll with the customer + node identity to receive
       a fresh bearer token + node_id
    3. Installs C:\atlas-pos\posd\, writes config.json from the enrollment
       response, installs pip deps, registers Startup .lnk
    4. Boots the agent and verifies /health
    5. Pushes an immediate baseline mirror so the cockpit shows green from
       second one
#>

param(
    [Parameter(Mandatory=$true)][string]$CustomerId,           # short slug, e.g. "venue-a", "venue_e"
    [string]$CustomerName = $null,                              # full display name; omit if customer already exists
    [string]$NodeIdHint = $null,                                # e.g. "kassa-01" — server may auto-name if omitted
    [string]$Label = $null,                                     # human label, e.g. "Bar (links)"
    [int]$OdooPartnerId = 0,                                    # optional Odoo res.partner id
    [string]$CollectorUrl = "http://192.0.2.10:8087",
    [Parameter(Mandatory=$true)][string]$EnrollmentToken        # from pos-hub fleet.json enrollment.token
)

$ErrorActionPreference = 'Stop'
function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Err($msg)  { Write-Host "    $msg" -ForegroundColor Red }

# ----------------------------------------------------------------------------
Step "Tailscale check"
$ts = & "C:\Program Files\Tailscale\tailscale.exe" ip -4 2>$null
if (-not $ts) { Err "Tailscale not connected. Sign into Tailscale first."; exit 1 }
$tsIp = ($ts -split "`n")[0].Trim()
Ok "tailnet IP: $tsIp"

# ----------------------------------------------------------------------------
Step "Calling enrollment endpoint at $CollectorUrl"
$body = @{
    customer_id     = $CustomerId
    customer_name   = $CustomerName
    node_id         = $NodeIdHint
    label           = $Label
    tailnet_ip      = $tsIp
    port            = 8765
    odoo_partner_id = if ($OdooPartnerId -gt 0) { $OdooPartnerId } else { $null }
} | ConvertTo-Json
$resp = Invoke-RestMethod -Uri "$CollectorUrl/api/enroll" -Method Post -ContentType 'application/json' `
                          -Headers @{ Authorization = "Bearer $EnrollmentToken" } -Body $body -TimeoutSec 15
Ok "node_id   = $($resp.node_id)"
Ok "customer  = $($resp.customer_id)"

# ----------------------------------------------------------------------------
Step "Staging C:\atlas-pos\posd"
New-Item -ItemType Directory -Path C:\atlas-pos\posd -Force | Out-Null
$pkg = Join-Path $PSScriptRoot 'posd-package'
if (-not (Test-Path $pkg)) { Err "missing posd-package next to bootstrap.ps1"; exit 1 }
Copy-Item "$pkg\*" C:\atlas-pos\posd\ -Recurse -Force
Ok "files copied"

# ----------------------------------------------------------------------------
Step "Writing config.json"
$cfg = @{
    node_id       = $resp.node_id
    customer_id   = $resp.customer_id
    collector_url = $CollectorUrl
    bind_host     = $tsIp
    bind_port     = $resp.agent_port
    bearer_token  = $resp.token
    mysql         = @{
        host     = "192.0.2.10"
        port     = 3306
        user     = "root"
        password = "<MYSQL_PASSWORD>"   # NOTE: rotate later via vault.set
        database = "kassa"
    }
    backup_dir = "C:\atlas-pos\posd\backups"
    mysqldump  = "C:\xampp\mysql\bin\mysqldump.exe"
}
$cfg | ConvertTo-Json -Depth 5 | Set-Content C:\atlas-pos\posd\config.json -Encoding utf8
Ok "config written"

# ----------------------------------------------------------------------------
Step "Installing Python deps"
& py -3 -m pip install -q -r C:\atlas-pos\posd\requirements.txt 2>&1 | Select-Object -Last 2
Ok "deps installed"

# ----------------------------------------------------------------------------
Step "Opening firewall + adding autostart .lnk"
$rule = Get-NetFirewallRule -DisplayName "Atlas POS-Ops agent" -ErrorAction SilentlyContinue
if (-not $rule) {
    New-NetFirewallRule -DisplayName "Atlas POS-Ops agent" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Any | Out-Null
}
$startup = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$lnk = Join-Path $startup 'AtlasPOSd.lnk'
$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = 'C:\Windows\System32\wscript.exe'
$s.Arguments  = '"C:\atlas-pos\posd\run.vbs"'
$s.WorkingDirectory = 'C:\atlas-pos\posd'
$s.Description = "Atlas POS-Ops agent ($($resp.customer_id)/$($resp.node_id))"
$s.WindowStyle = 7
$s.Save()
Ok "firewall + autostart wired"

# ----------------------------------------------------------------------------
Step "Booting agent + verifying"
Get-Process python -ErrorAction SilentlyContinue | Where-Object {$_.Path -like "*pythoncore*"} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Process wscript.exe -ArgumentList '"C:\atlas-pos\posd\run.vbs"'
Start-Sleep 4
try {
    $health = Invoke-RestMethod -Uri "http://${tsIp}:8765/health" -TimeoutSec 5
    Ok "agent up: db_reachable=$($health.db_reachable) kassa=$($health.kassa_running)"
} catch {
    Err "health probe failed: $($_.Exception.Message)"
    exit 1
}

# ----------------------------------------------------------------------------
Step "Pushing baseline mirror"
$h = @{ Authorization = "Bearer $($resp.token)" }
try {
    $snap = Invoke-RestMethod -Uri "http://${tsIp}:8765/snapshot?mirror=true" -Method Post -Headers $h -TimeoutSec 60
    Ok "baseline mirror: $($snap.size) bytes, sha=$($snap.sha256.Substring(0,12))..."
} catch {
    Err "mirror push failed (agent still works locally): $($_.Exception.Message)"
}

Write-Host ""
Write-Host "DONE." -ForegroundColor Green
Write-Host "Cockpit will show this terminal within 30 seconds:" -ForegroundColor Green
Write-Host "  $CollectorUrl/" -ForegroundColor White
