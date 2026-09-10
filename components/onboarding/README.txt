Atlas POS-Ops onboarding kit
============================

Drop this whole folder on a fresh POS terminal. Then, from an elevated
PowerShell prompt in this directory, run:

  .\bootstrap.ps1 `
      -CustomerId   "venue-a" `
      -CustomerName "Venue A" `
      -Label        "Bar (links)" `
      -OdooPartnerId 42 `
      -EnrollmentToken "<get from pos-hub:/opt/atlas/posops/fleet.json .enrollment.token>"

What it does:
  - Reads the local Tailscale IP
  - Calls pos-hub /api/enroll to register this terminal (gets back node_id + bearer token)
  - Installs the agent at C:\atlas-pos\posd, writes config.json
  - Adds Windows firewall rule (TCP 8765 inbound) + autostart shortcut
  - Boots the agent and pushes a baseline mirror so the cockpit goes green
    within 30 seconds

Required on the terminal beforehand:
  - Windows 10/11 with Python 3.11+ (py.exe in PATH)
  - Tailscale signed in (any tailnet account on the Atlas tailnet)
  - XAMPP MySQL with the kassa DB (root password baked into config; rotate
    later via the vault.set typed op)
