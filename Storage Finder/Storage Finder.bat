@echo off
title Storage Finder
set "APP=%~dp0StorageFinder.pyw"

if not exist "%APP%" (
  echo Could not find StorageFinder.pyw next to this file.
  pause
  exit /b 1
)

rem --- Try the Python launcher, then pythonw ---
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw -3 "%APP%"
  exit /b 0
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "%APP%"
  exit /b 0
)

rem --- Python not found: offer to install it ---
echo Storage Finder needs Python, which is not installed on this PC.
echo.
choice /c YN /m "Install Python now (free, about 1 minute)"
if errorlevel 2 exit /b 1

where winget >nul 2>nul
if not %errorlevel%==0 (
  echo winget is not available. Opening the Python download page instead.
  echo During setup, tick "Add python.exe to PATH", then run this file again.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)

winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements

set "PYW=%LocalAppData%\Programs\Python\Python312\pythonw.exe"
if exist "%PYW%" (
  start "" "%PYW%" "%APP%"
  exit /b 0
)

echo Python was installed. Close this window and double-click this file again.
pause
