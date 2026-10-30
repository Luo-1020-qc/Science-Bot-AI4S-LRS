@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-ScienceBot.ps1" -Interface web %*
