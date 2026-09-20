@echo off
cd /d "%~dp0"
echo Dang khoi chay Auto Video Translator...
"venv\Scripts\python.exe" main.py
if errorlevel 1 pause
