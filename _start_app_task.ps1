$ErrorActionPreference = 'SilentlyContinue'
$dir   = 'c:\Users\Ops\OneDrive\Desktop\dev\Glory2YahPub - Copy'
$task  = 'Glory2YahPub_Dev'
$wrapper = Join-Path $dir '_run_app_detached.cmd'

# Stop any existing app instance (ours only) and old scheduled task
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*_run_server.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
schtasks /End /TN $task 2>$null | Out-Null
schtasks /Delete /TN $task /F 2>$null | Out-Null

# Create + run a one-shot scheduled task (fully detached from this shell)
$tr = '"' + $wrapper + '"'
schtasks /Create /F /TN $task /TR $tr /SC ONCE /ST 23:59 /RL LIMITED | Out-Null
schtasks /Run /TN $task | Out-Null

Start-Sleep -Seconds 12
Write-Output '--- running flag result ---'
schtasks /Query /TN $task 2>$null
Write-Output '--- python listeners ---'
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in 5000, 8080 } |
  Select-Object LocalAddress, LocalPort, OwningProcess
Write-Output '--- log tail ---'
Get-Content (Join-Path $dir 'logs\run_manual_app.err.log') -Tail 8 -ErrorAction SilentlyContinue