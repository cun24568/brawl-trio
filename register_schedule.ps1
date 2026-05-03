# 3時間ごとに daily_update.bat を実行するタスクをWindowsタスクスケジューラに登録
# 使い方: PowerShellで実行
#   powershell -ExecutionPolicy Bypass -File register_schedule.ps1

$taskName = "BrawlTrioCrawl"
$batPath = "C:\Users\himas\OneDrive\デスクトップ\code\brawl-trio\daily_update.bat"

if (-not (Test-Path $batPath)) {
    Write-Host "ERROR: $batPath が見つかりません"
    exit 1
}

# 既存タスクがあれば削除
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "既存のタスクを削除します..."
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# アクション: .bat 実行
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batPath`""

# トリガー: 1分後から1時間ごと(無期限)
$startTime = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startTime `
    -RepetitionInterval (New-TimeSpan -Hours 1) `
    -RepetitionDuration ([TimeSpan]::MaxValue)

# 設定: バッテリー駆動でも実行、隠して実行
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# 登録
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Brawl Stars トリオサバイバル データ収集 (3時間ごと)" `
    -Force

Write-Host ""
Write-Host "✓ タスク登録完了: $taskName"
Write-Host "  開始: $startTime"
Write-Host "  間隔: 1時間ごと"
Write-Host ""
Write-Host "確認: タスクスケジューラを開いて 'BrawlTrioCrawl' を探す"
Write-Host "削除: powershell -Command `"Unregister-ScheduledTask -TaskName 'BrawlTrioCrawl' -Confirm:`$false`""
