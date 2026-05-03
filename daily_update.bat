@echo off
REM 1時間ごと実行用: クロール + DB再ビルド + git push
REM register_schedule.ps1 でタスクスケジューラに登録

cd /d "%~dp0"
echo ====================================
echo Brawl Trio Crawler - %DATE% %TIME%
echo ====================================
py crawl_full.py
if errorlevel 1 goto :error
py build_db.py
if errorlevel 1 goto :error

REM Vercel 自動デプロイ用に db.json だけ push
git add data/db.json
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "auto: data update %DATE% %TIME%"
    git push
    echo === Pushed to remote ===
) else (
    echo === No data changes, skip push ===
)

echo.
echo === Done ===
exit /b 0

:error
echo === FAILED ===
exit /b 1
