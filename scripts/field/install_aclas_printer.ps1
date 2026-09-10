# Deploy ACLAS LAN kitchen printer to a remote POS — silent, no GUI.
# Strategy: add raw TCP/IP port at port 9100, attach "Generic / Text Only" driver
# (Windows built-in). kassa.exe sends ESC/POS bytes directly, so we don't need
# the ACLAS GUI installer at all. Zero windows on the POS user's screen.
#
# Args via env vars before invoke:
#   $env:ACLAS_IP       = printer IP (required, e.g. 192.168.1.50)
#   $env:ACLAS_NAME     = Windows printer name (default: "ACLAS Keuken")
#   $env:ACLAS_TESTPRINT = "1" to send test print (default: "1")
#
# Run via:
#   $env:ACLAS_IP="192.168.x.x"; iex (New-Object System.Net.WebClient).DownloadString("http://<VPS-IP>/setup/pos_deploy_aclas.ps1")

$ErrorActionPreference = 'SilentlyContinue'
$out = [ordered]@{}

if (-not $env:ACLAS_IP) { Write-Output 'ERROR: env:ACLAS_IP required'; return }
$ip = $env:ACLAS_IP
$name = if ($env:ACLAS_NAME) { $env:ACLAS_NAME } else { 'ACLAS Keuken' }
$portName = "ACLAS_$($ip -replace '\.','_')_9100"
$driver = 'Generic / Text Only'

$out.target = $ip
$out.name = $name
$out.port = $portName
$out.driver = $driver

# Step 1: Reachability check
$tcp = New-Object System.Net.Sockets.TcpClient
try {
    $task = $tcp.ConnectAsync($ip, 9100)
    $reachable = $task.Wait(2000) -and $tcp.Connected
} catch { $reachable = $false }
finally { $tcp.Close() }
$out.reachable = $reachable
if (-not $reachable) {
    Write-Output ($out | ConvertTo-Json)
    Write-Output "ABORT: printer at $ip not reachable on port 9100"
    return
}

# Step 2: Get HTTP banner to confirm it's the ACLAS printer
try {
    $r = Invoke-WebRequest "http://$ip" -TimeoutSec 3 -UseBasicParsing
    $title = ([regex]'<title[^>]*>(.*?)</title>').Match($r.Content).Groups[1].Value
    $out.http_title = $title
    $out.http_server = ($r.Headers.Server -join ',')
} catch {
    $out.http_err = $_.Exception.Message
}

# Step 3: Add TCP/IP raw port (idempotent)
$existing = Get-PrinterPort -Name $portName -ErrorAction SilentlyContinue
if (-not $existing) {
    try {
        Add-PrinterPort -Name $portName -PrinterHostAddress $ip -PortNumber 9100
        $out.port_added = $true
    } catch {
        $out.port_err = $_.Exception.Message
    }
} else {
    $out.port_added = $false
    $out.port_existing = "$($existing.PrinterHostAddress):$($existing.PortNumber)"
}

# Step 4: Ensure Generic / Text Only driver is installed (it's built-in on all Windows)
$drvInstalled = Get-PrinterDriver -Name $driver -ErrorAction SilentlyContinue
if (-not $drvInstalled) {
    try {
        Add-PrinterDriver -Name $driver -ErrorAction Stop
        $out.driver_added = $true
    } catch {
        $out.driver_err = $_.Exception.Message
    }
} else {
    $out.driver_added = $false
}

# Step 5: Add the printer (idempotent)
$existPrinter = Get-Printer -Name $name -ErrorAction SilentlyContinue
if (-not $existPrinter) {
    try {
        Add-Printer -Name $name -DriverName $driver -PortName $portName
        $out.printer_added = $true
    } catch {
        $out.printer_err = $_.Exception.Message
    }
} else {
    $out.printer_added = $false
    $out.printer_existing = "$($existPrinter.DriverName)/$($existPrinter.PortName)"
}

# Step 6: Send a non-disruptive raw test print (ESC/POS init + small text + cut)
$sendTest = if ($env:ACLAS_TESTPRINT -eq '0') { $false } else { $true }
if ($sendTest) {
    try {
        $tcp2 = New-Object System.Net.Sockets.TcpClient($ip, 9100)
        $stream = $tcp2.GetStream()
        $esc_init = [byte[]](0x1B, 0x40)  # ESC @ init
        $stream.Write($esc_init, 0, $esc_init.Length)
        $msg = "`n=== ATLAS ACLAS TEST ===`n$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`nPrinter: $name`nIP: $ip`nKeuken klaar voor gebruik.`n`n`n`n"
        $bytes = [Text.Encoding]::ASCII.GetBytes($msg)
        $stream.Write($bytes, 0, $bytes.Length)
        $cut = [byte[]](0x1D, 0x56, 0x00)  # GS V 0 = full cut
        $stream.Write($cut, 0, $cut.Length)
        $stream.Flush()
        Start-Sleep -Milliseconds 300
        $stream.Close()
        $tcp2.Close()
        $out.test_print_sent = $true
    } catch {
        $out.test_print_err = $_.Exception.Message
    }
}

# Step 7: Final state confirmation
$out.final = Get-Printer -Name $name | Select-Object Name, DriverName, PortName

Write-Output "===DEPLOY_RESULT==="
Write-Output ($out | ConvertTo-Json -Depth 5)
Write-Output "===DEPLOY_END==="
