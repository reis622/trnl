@echo off
rem Optional alternative to the one-line installer: put install.ps1 (and optionally a trnl-*.whl)
rem next to this file and double-click it. Without a wheel it installs the latest GitHub release.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 pause
