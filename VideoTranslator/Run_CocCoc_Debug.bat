@echo off
title Mo Coc Coc Debug Mode (Port 9223)
echo ========================================================
echo   DANG KHOI DONG COC COC O CHE DO DEBUG (PORT 9223)
echo ========================================================
echo.
echo 1. Dang tat cac tien trinh Coc Coc dang chay...
taskkill /F /IM browser.exe /T >nul 2>&1
taskkill /F /IM coccoc.exe /T >nul 2>&1

:: Cho toi da 2 giay de tien trinh dong han
timeout /t 2 /nobreak >nul

echo 2. Dang khoi chay Coc Coc voi cong 9223...
start "" "C:\Program Files\CocCoc\Browser\Application\browser.exe" --remote-debugging-port=9223

echo 3. Dang kiem tra ket noi port 9223...
powershell -Command "$ok = $false; for ($i=0; $i -lt 8; $i++) { Start-Sleep -Milliseconds 500; if (Get-NetTCPConnection -LocalPort 9223 -ErrorAction SilentlyContinue) { $ok = $true; break } }; if ($ok) { Write-Host '>>> KET NOI THANH CONG! Trinh duyet da san sang.' -ForegroundColor Green } else { Write-Host '>>> CHUA KET NOI DUOC PORT 9223. Hay chay lai file nay.' -ForegroundColor Red }"

echo.
echo ========================================================
echo   LUU Y: Giu nguyen cua so Coc Coc nay.
echo   Mo tab ChatGPT (chatgpt.com) hoac Gemini (gemini.google.com)
echo   Sau do bat Tool va an 'BAT DAU'.
echo ========================================================
echo.
pause
