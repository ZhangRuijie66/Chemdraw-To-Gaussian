@echo off
setlocal
cd /d "%~dp0"

rem Preferred: the shared no-console launcher from the parent workspace.
if exist "%~dp0..\_tools\hidden-launch.vbs" (
    wscript.exe //NoLogo "%~dp0..\_tools\hidden-launch.vbs" "%~dp0."
    exit /b
)

rem Standalone copy (GitHub source ZIP / renamed folder): no shared _tools.
echo.
echo  ==============================================
echo   Gaussian Input Generator - standalone
echo  ==============================================
echo  Shared _tools launcher not found; using the local launcher.
echo.

set "PY="
if exist "C:\Python311\python.exe" set "PY=C:\Python311\python.exe"
if not defined PY if exist "C:\Python313\python.exe" set "PY=C:\Python313\python.exe"
if not defined PY if exist "C:\Python312\python.exe" set "PY=C:\Python312\python.exe"
if not defined PY if exist "C:\Python310\python.exe" set "PY=C:\Python310\python.exe"
if not defined PY if exist "C:\Python39\python.exe"  set "PY=C:\Python39\python.exe"
if not defined PY (
  python -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  py -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PY=py"
)
if not defined PY (
  echo  [ERROR] Python 3 not found.
  echo  Install Python 3.10+ from https://www.python.org/downloads/,
  echo  or use the portable package ^(its root launcher needs no Python setup^).
  echo.
  pause
  exit /b 1
)

echo  Python : %PY%
"%PY%" -c "import sys; print('  Version:', sys.version.split()[0])"

"%PY%" -c "import rdkit, numpy, matplotlib" >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Installing missing packages ^(first run only, needs internet^) ...
  "%PY%" -m pip install rdkit numpy matplotlib paramiko -i https://pypi.tuna.tsinghua.edu.cn/simple
  "%PY%" -c "import rdkit" >nul 2>nul
  if errorlevel 1 (
    echo.
    echo  [ERROR] rdkit install failed. Check your network, or install manually:
    echo    pip install rdkit -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause
    exit /b 1
  )
)

echo.
echo  Starting ... ^(close this window to stop^)
"%PY%" "%~dp0run.py"
if errorlevel 1 pause
