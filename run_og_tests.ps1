$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location "c:\Users\Ops\OneDrive\Desktop\dev\Glory2YahPub - Copy"
python -u test_og_preview_ads.py 2>&1 | Tee-Object -FilePath og_tests.log
Write-Host "EXIT=$LASTEXITCODE"
