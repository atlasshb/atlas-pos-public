$ErrorActionPreference = 'SilentlyContinue'
$out = [ordered]@{}
$out.host = $env:COMPUTERNAME
$out.user = $env:USERNAME
$out.os = (Get-WmiObject Win32_OperatingSystem).Caption
$out.ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

# Network
$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^(127|169)' }
$out.ips = $ips | Select-Object IPAddress, InterfaceAlias, PrefixLength
$out.gateway = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Select-Object -First 1 -ExpandProperty NextHop)

# Printers
$out.printers = Get-Printer | Select-Object Name, DriverName, PortName, Shared
$out.printer_ports = Get-PrinterPort | Select-Object Name, Description, PrinterHostAddress, PortNumber

# COM ports
$out.com_ports = Get-PnpDevice -Class Ports -PresentOnly | Select-Object FriendlyName, Status

# Kassa
$kp = Get-Process kassa -ErrorAction SilentlyContinue | Select-Object -First 1
$out.kassa_running = [bool]$kp
if ($kp) {
    $out.kassa_path = $kp.Path
    $kdir = Split-Path $kp.Path
    $out.kassa_dir = $kdir
    $out.kassa_files = Get-ChildItem $kdir -File | Select-Object Name, Length, LastWriteTime
    $bcf = Join-Path $kdir 'kassa.bcf'
    if (Test-Path $bcf) {
        $out.kassa_bcf_b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($bcf))
        $out.kassa_bcf_size = (Get-Item $bcf).Length
    }
    $cfgs = Get-ChildItem $kdir -File | Where-Object { $_.Extension -match '\.(ini|cfg|conf|xml|json|txt|bcf)$' -and $_.Length -lt 100000 }
    $out.kassa_configs = @{}
    foreach ($f in $cfgs) {
        try {
            $bytes = [IO.File]::ReadAllBytes($f.FullName)
            $out.kassa_configs[$f.Name] = [Convert]::ToBase64String($bytes)
        } catch {}
    }
}

# MySQL
$out.mysql_svc = Get-Service -Name 'MySQL*','mariadb*' | Select-Object Name, Status
$out.mysql_listen = Get-NetTCPConnection -State Listen -LocalPort 3306 -ErrorAction SilentlyContinue | Select-Object LocalAddress

# Installed POS software
$out.installed_pos = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' | Where-Object { $_.DisplayName -match 'kassa|optimum|pos|epson|aclas|citizen|star|splashtop|verifone|yomani|sam4s|snbc' } | Select-Object DisplayName, DisplayVersion, InstallDate

# Splashtop
$out.splashtop_svc = Get-Service -Name '*splashtop*' | Select-Object Name, Status

# ARP (active LAN hosts)
$out.arp = (arp -a) -split "`n" | Where-Object { $_ -match '\d+\.\d+\.\d+\.\d+' } | ForEach-Object { $_.Trim() }

# Quick 9100 scan on known ARP hosts only (way faster than /24 sweep)
$out.printers_at_9100 = @()
foreach ($line in $out.arp) {
    if ($line -match '(\d+\.\d+\.\d+\.\d+)') {
        $ip = $matches[1]
        $tcp = New-Object System.Net.Sockets.TcpClient
        try {
            $t = $tcp.ConnectAsync($ip, 9100)
            if ($t.Wait(300) -and $tcp.Connected) {
                $out.printers_at_9100 += $ip
            }
        } catch {} finally { $tcp.Close() }
    }
}

# HTTP banner grab for ARP hosts
$out.http_banners = @{}
foreach ($line in $out.arp) {
    if ($line -match '(\d+\.\d+\.\d+\.\d+)') {
        $ip = $matches[1]
        try {
            $r = Invoke-WebRequest -Uri "http://$ip/" -TimeoutSec 1 -UseBasicParsing -ErrorAction SilentlyContinue
            if ($r) {
                $title = ([regex]'<title[^>]*>(.*?)</title>').Match($r.Content).Groups[1].Value
                $out.http_banners[$ip] = @{ status = $r.StatusCode; title = $title; server = ($r.Headers.Server -join ',') }
            }
        } catch {}
    }
}

# Output: marker, base64 JSON chunks, marker
$json = $out | ConvertTo-Json -Depth 8 -Compress
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
Write-Output "===POS_COLLECT_START==="
Write-Output "LEN=$($b64.Length)"
for ($i = 0; $i -lt $b64.Length; $i += 240) {
    $end = [Math]::Min($i + 240, $b64.Length)
    Write-Output $b64.Substring($i, $end - $i)
}
Write-Output "===POS_COLLECT_END==="
