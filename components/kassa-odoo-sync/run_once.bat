@echo off
REM Atlas POS -> Odoo: single sync pass (dry-run unless apply=1 in config.ini)
cd /d "%~dp0"
py -3 sync.py --once
pause
