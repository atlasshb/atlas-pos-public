@echo off
REM Atlas POS -> Odoo: continuous sync every interval_seconds (config.ini)
cd /d "%~dp0"
py -3 sync.py --loop
