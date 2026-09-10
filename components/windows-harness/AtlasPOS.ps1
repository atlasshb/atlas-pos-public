#requires -Version 5.1
<#
  Atlas POS launcher / harness.

  This is a thin shell around the vendor's kassa.exe. It does NOT replace the POS
  -- it boots kassa.exe and continuously rewrites its visible chrome (window
  titles, optional auto-dismissal of vendor info popups) so the operator sees
  Atlas POS, never DoPos/OptimumPOS.

  Behaviour:
    1. Launch kassa.exe if not already running.
    2. Loop every 250 ms:
         - Find any kassa.exe windows of class UPP-CLASS-W.
         - Rewrite known vendor titles to Atlas equivalents.
         - If $AutoDismissInfo, send WM_CLOSE to the "Info" popup as it appears.
    3. Exit when kassa.exe exits.

  Replaces C:\kassa\kassa.lnk in Startup with a shortcut to this script.
#>

param(
    [string]$KassaExe = 'C:\kassa\kassa.exe',
    [string]$KassaCwd = 'C:\kassa',
    [int]$PollMs = 250,
    [switch]$AutoDismissInfo,
    [switch]$Verbose
)

Add-Type -Namespace AtlasHarness -Name Win -MemberDefinition @'
public delegate bool EnumWindowsProc(System.IntPtr hWnd, System.IntPtr lParam);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool EnumWindows(EnumWindowsProc enumProc, System.IntPtr lParam);
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet=System.Runtime.InteropServices.CharSet.Auto, SetLastError=true)]
public static extern int GetWindowText(System.IntPtr hWnd, System.Text.StringBuilder text, int count);
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet=System.Runtime.InteropServices.CharSet.Auto)]
public static extern int GetClassName(System.IntPtr hWnd, System.Text.StringBuilder text, int count);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern uint GetWindowThreadProcessId(System.IntPtr hWnd, out uint processId);
[System.Runtime.InteropServices.DllImport("user32.dll", CharSet=System.Runtime.InteropServices.CharSet.Auto, SetLastError=true)]
public static extern bool SetWindowText(System.IntPtr hWnd, string text);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool IsWindowVisible(System.IntPtr hWnd);
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern System.IntPtr SendMessage(System.IntPtr hWnd, uint msg, System.IntPtr wParam, System.IntPtr lParam);
'@

# --- Title translation table -------------------------------------------------
# Anything matching the LHS gets rewritten to the RHS. Match is case-sensitive
# exact match against the current window title.
$Translate = @{
    'OptimumPOS'                        = 'Atlas POS'
    'Optimum POS'                       = 'Atlas POS'
    'DoPos'                             = 'Atlas POS'
    'DoBizz'                            = 'Atlas POS'
    'Kassa'                             = 'Atlas POS'
    'Kassa ontgrendelen'                = 'Atlas POS - vergrendeld'
    'Pin invoer'                        = 'Atlas POS - PIN invoer'
    'Instellingen'                      = 'Atlas POS - Instellingen'
}

# Substring -> replacement, applied after exact-match lookup misses. Useful for
# popups whose title includes the vendor brand somewhere in the middle.
$SubReplace = [ordered]@{
    'OptimumPOS' = 'Atlas POS'
    'Optimum POS' = 'Atlas POS'
    'DoPos' = 'Atlas POS'
    'DoBizz' = 'Atlas POS'
}

$KassaTitlesToDismiss = @(
    # Add titles here that the harness should auto-close. Off by default.
    # 'Info'
)

# --- Launch kassa.exe --------------------------------------------------------
$proc = Get-Process kassa -ErrorAction SilentlyContinue
if (-not $proc) {
    Write-Host "[AtlasPOS] launching $KassaExe ..."
    Start-Process -FilePath $KassaExe -WorkingDirectory $KassaCwd
    Start-Sleep -Milliseconds 1500
    $proc = Get-Process kassa -ErrorAction SilentlyContinue
}
if (-not $proc) {
    Write-Error "[AtlasPOS] kassa.exe failed to start"
    exit 1
}
$kassaPid = [uint32]$proc.Id
Write-Host "[AtlasPOS] kassa.exe PID=$kassaPid - harness active"

# --- Harness loop ------------------------------------------------------------
$WM_CLOSE = 0x0010
$relabeled = @{}  # hwnd -> title we last set (avoid spamming SetWindowText)

while ($true) {
    $alive = Get-Process -Id $kassaPid -ErrorAction SilentlyContinue
    if (-not $alive) {
        Write-Host "[AtlasPOS] kassa.exe exited - harness shutting down"
        break
    }

    [AtlasHarness.Win]::EnumWindows({
        param($hWnd, $lParam)
        $wpid = 0
        [void][AtlasHarness.Win]::GetWindowThreadProcessId($hWnd, [ref]$wpid)
        if ($wpid -ne $kassaPid) { return $true }

        $cls = New-Object System.Text.StringBuilder 128
        [void][AtlasHarness.Win]::GetClassName($hWnd, $cls, 128)
        if ($cls.ToString() -notlike 'UPP-*') { return $true }

        $cur = New-Object System.Text.StringBuilder 256
        [void][AtlasHarness.Win]::GetWindowText($hWnd, $cur, 256)
        $title = $cur.ToString()
        if ([string]::IsNullOrEmpty($title)) { return $true }

        if ($AutoDismissInfo -and ($KassaTitlesToDismiss -contains $title)) {
            [void][AtlasHarness.Win]::SendMessage($hWnd, $WM_CLOSE, [IntPtr]::Zero, [IntPtr]::Zero)
            if ($Verbose) { Write-Host "[AtlasPOS] dismissed '$title' (hwnd=$hWnd)" }
            return $true
        }

        $new = $null
        if ($Translate.ContainsKey($title)) {
            $new = $Translate[$title]
        } else {
            foreach ($k in $SubReplace.Keys) {
                if ($title -like "*$k*") {
                    $new = $title.Replace($k, $SubReplace[$k])
                    break
                }
            }
        }
        if ($new -and $new -ne $title -and $relabeled[$hWnd] -ne $new) {
            [void][AtlasHarness.Win]::SetWindowText($hWnd, $new)
            $relabeled[$hWnd] = $new
            if ($Verbose) { Write-Host "[AtlasPOS] '$title' -> '$new'" }
        }
        return $true
    }, [IntPtr]::Zero) | Out-Null

    Start-Sleep -Milliseconds $PollMs
}
