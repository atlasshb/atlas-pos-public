# Install ACLAS LAN kitchen printer on a remote POS.
# Run via DWS shell — `iex (New-Object System.Net.WebClient).DownloadString('http://<VPS-IP>/setup/pos_install_aclas.ps1')`
# Args via env vars:
#   $env:ACLAS_IP   = target printer IP (e.g. 192.168.1.50)
#   $env:ACLAS_NAME = Windows printer display name (default: "ACLAS Keuken")
#   $env:ACLAS_DRIVER = driver name to use (default: try "Generic / Text Only")

$ErrorActionPreference = 'SilentlyContinue'
$out = [ordered]@{}

if (-not $env:ACLAS_IP) { Write-Output 'ERROR: $env:ACLAS_IP not set'; exit 1 }
$name = if ($env:ACLAS_NAME) { $env:ACLAS_NAME } else { 'ACLAS Keuken' }
$driver = if ($env:ACLAS_DRIVER) { $env:ACLAS_DRIVER } else { 'Generic / Text Only' }
$portName = "ACLAS_$($env:ACLAS_IP -replace '\.','_')"

$out.target_ip = $env:ACLAS_IP
$out.name = $name
$out.driver = $driver
$out.port = $portName

# Step 1: reachability check
$tcp = New-Object System.Net.Sockets.TcpClient
$t = $tcp.ConnectAsync($env:ACLAS_IP, 9100)
$reachable = $t.Wait(2000) -and $tcp.Connected
$tcp.Close()
$out.reachable_9100 = $reachable
if (-not $reachable) { Write-Output ($out | ConvertTo-Json); exit 2 }

# Step 2: HTTP banner (identify model)
try {
    $r = Invoke-WebRequest "http://$($env:ACLAS_IP)" -TimeoutSec 3 -UseBasicParsing
    $out.http_title = ([regex]'<title[^>]*>(.*?)</title>').Match($r.Content).Groups[1].Value
    $out.http_server = $r.Headers.Server
} catch { $out.http_err = $_.Exception.Message }

# Step 3: add TCP/IP port if not exists
$existing = Get-PrinterPort -Name $portName -ErrorAction SilentlyContinue
if (-not $existing) {
    Add-PrinterPort -Name $portName -PrinterHostAddress $env:ACLAS_IP -PortNumber 9100
    $out.port_added = $true
} else {
    $out.port_added = $false
    $out.port_existing_host = $existing.PrinterHostAddress
}

# Step 4: install printer with given driver
$existing_printer = Get-Printer -Name $name -ErrorAction SilentlyContinue
if (-not $existing_printer) {
    Add-Printer -Name $name -DriverName $driver -PortName $portName
    $out.printer_added = $true
} else {
    $out.printer_added = $false
    $out.printer_existing_driver = $existing_printer.DriverName
}

# Step 5: send raw test print (CR + LF + ESC + 4 lines + paper-cut)
try {
    $tcp2 = New-Object System.Net.Sockets.TcpClient($env:ACLAS_IP, 9100)
    $stream = $tcp2.GetStream()
    $bytes = [Text.Encoding]::ASCII.GetBytes("`r`n=== ACLAS TEST FROM ATLAS ===`r`n$(Get-Date)`r`nKitchen printer ready.`r`n`r`n`r`n")
    $stream.Write($bytes, 0, $bytes.Length)
    # ESC i = full cut
    $cut = [byte[]]@(0x1B, 0x69)
    $stream.Write($cut, 0, $cut.Length)
    $stream.Close()
    $tcp2.Close()
    $out.test_print_sent = $true
} catch {
    $out.test_print_err = $_.Exception.Message
}

# Step 6: verify printer queue
$out.final_printer = Get-Printer -Name $name | Select-Object Name, DriverName, PortName

Write-Output ($out | ConvertTo-Json -Depth 4)
