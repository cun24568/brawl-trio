@echo off
REM 毎日実行用: クロール + DB再ビルド
REM Windows Task Scheduler に登録すれば自動化可能
REM 「コンピュータの管理」→「タスクスケジューラ」→ 基本タスク作成
REM   トリガー: 毎日 / 開始時刻 (例 06:00)
REM   操作: プログラム = この .bat ファイル

cd /d "%~dp0"
echo ====================================
echo Brawl Trio Crawler - %DATE% %TIME%
echo ====================================
py crawl_full.py
if errorlevel 1 goto :error
py build_db.py
if errorlevel 1 goto :error
echo.
echo === Done ===
exit /b 0

:error
echo === FAILED ===
exit /b 1
