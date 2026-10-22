@echo off
setlocal
title Gaussian Input Generator
cd /d "%~dp0"

set "PY="
if exist "C:\Python311\python.exe" set "PY=C:\Python311\python.exe"
if not defined PY if exist "C:\Python313\python.exe" set "PY=C:\Python313\python.exe"
if not defined PY if exist "C:\Python312\python.exe" set "PY=C:\Python312\python.exe"
if not defined PY (
  python -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo  [ERROR] Python 3 not found.
  pause
  exit /b 1
)

"%PY%" -c "import rdkit" >nul 2>nul
if errorlevel 1 (
  echo  Installing RDKit ^(first run only^) ...
  "%PY%" -m pip install rdkit -i https://pypi.tuna.tsinghua.edu.cn/simple
)

"%PY%" -c "import paramiko" >nul 2>nul
if errorlevel 1 (
  echo  Installing paramiko ^(SSH^) ...
  "%PY%" -m pip install paramiko -i https://pypi.tuna.tsinghua.edu.cn/simple
)

"%PY%" "%~dp0run.py"
pause
