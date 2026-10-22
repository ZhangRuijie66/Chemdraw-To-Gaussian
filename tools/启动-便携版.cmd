@echo off
setlocal
title Gaussian Input Generator (Portable)
cd /d "%~dp0"

echo.
echo  ==============================================
echo   Gaussian Input Generator  -  portable edition
echo  ==============================================
echo.

rem ---- locate a usable Python ------------------------------------------
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
  echo  Please install Python 3.10+ from https://www.python.org/downloads/
  echo  and tick "Add python.exe to PATH" during setup.
  echo.
  pause
  exit /b 1
)

echo  Python : %PY%
"%PY%" -c "import sys; print('  Version:', sys.version.split()[0])"

rem ---- rdkit / numpy / matplotlib -------------------------------------
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
"%PY%" "高斯计算工具\run.py"

if errorlevel 1 (
  echo.
  echo  The program exited with an error. See the messages above.
  pause
)
