@echo off
cd /d "%~dp0"
echo ========================================================
echo   DANG DONG GOI UNG DUNG (PYINSTALLER)
echo ========================================================
echo.
"venv\Scripts\pyinstaller.exe" --noconfirm AutoVideoTranslator.spec
if errorlevel 1 (
    echo.
    echo [LOI] Dong goi that bai!
    pause
    exit /b 1
)
copy /Y "Run_CocCoc_Debug.bat" "dist\AutoVideoTranslator\" >nul
echo.
echo ========================================================
echo [THANH CONG] Ung dung da duoc dong goi tai thu muc: dist\AutoVideoTranslator\
echo ========================================================
echo.
pause
