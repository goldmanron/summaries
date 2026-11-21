@echo off
title Site Preview
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0preview.ps1" %*
pause
