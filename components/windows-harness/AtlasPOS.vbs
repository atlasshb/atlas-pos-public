' Atlas POS - hidden launcher shim.
' Starts AtlasPOS.ps1 with no visible PowerShell window.
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\atlas-pos\AtlasPOS.ps1""", 0, False
