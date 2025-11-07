# Glory2yahPub Comprehensive Testing Script
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Glory2yahPub Application Testing" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$baseUrl = "http://localhost:5000"
$testResults = @()

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Method = "GET"
    )
    
    try {
        Write-Host "Testing: $Name..." -NoNewline
        $response = Invoke-WebRequest -Uri $Url -Method $Method -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
        $status = $response.StatusCode
        $result = "PASS"
        $color = "Green"
        Write-Host " [$status] " -ForegroundColor $color -NoNewline
        Write-Host "PASS" -ForegroundColor $color
    }
    catch {
        $status = $_.Exception.Response.StatusCode.value__
        if ($status -eq 302 -or $status -eq 301) {
            $result = "REDIRECT"
            $color = "Yellow"
            Write-Host " [$status] " -ForegroundColor $color -NoNewline
            Write-Host "REDIRECT" -ForegroundColor $color
        }
        else {
            $result = "FAIL"
            $color = "Red"
            Write-Host " [$status] " -ForegroundColor $color -NoNewline
            Write-Host "FAIL" -ForegroundColor $color
        }
    }
    
    $script:testResults += [PSCustomObject]@{
        Name = $Name
        URL = $Url
        Status = $status
        Result = $result
    }
}

Write-Host "`n=== PUBLIC PAGES ===" -ForegroundColor Yellow
Test-Endpoint "Homepage" "$baseUrl/"
Test-Endpoint "Browse Ads (Achte)" "$baseUrl/achte"
Test-Endpoint "Submit Ad Page" "$baseUrl/submit_ad"
Test-Endpoint "Buy Gkach Page" "$baseUrl/achte_gkach"
Test-Endpoint "Success Page" "$baseUrl/success"

Write-Host "`n=== ADMIN PAGES ===" -ForegroundColor Yellow
Test-Endpoint "Admin Login Page" "$baseUrl/admin/login"
Test-Endpoint "Admin Dashboard (Protected)" "$baseUrl/admin"
Test-Endpoint "Manage Gkach (Protected)" "$baseUrl/admin/manage_gkach"

Write-Host "`n=== API ENDPOINTS ===" -ForegroundColor Yellow
Test-Endpoint "Welcome API" "$baseUrl/welcome"
Test-Endpoint "Gkach Rate API" "$baseUrl/api/gkach_rate"

Write-Host "`n=== STATIC RESOURCES ===" -ForegroundColor Yellow
Test-Endpoint "CSS Stylesheet" "$baseUrl/static/css/style.css"
Test-Endpoint "JavaScript" "$baseUrl/static/js/script.js"
Test-Endpoint "Service Worker" "$baseUrl/static/sw.js"
Test-Endpoint "Manifest" "$baseUrl/static/manifest.json"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "TEST SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$passed = ($testResults | Where-Object { $_.Result -eq "PASS" }).Count
$redirected = ($testResults | Where-Object { $_.Result -eq "REDIRECT" }).Count
$failed = ($testResults | Where-Object { $_.Result -eq "FAIL" }).Count
$total = $testResults.Count

Write-Host "`nTotal Tests: $total" -ForegroundColor White
Write-Host "Passed: $passed" -ForegroundColor Green
Write-Host "Redirected: $redirected" -ForegroundColor Yellow
Write-Host "Failed: $failed" -ForegroundColor Red

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "DETAILED RESULTS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
$testResults | Format-Table -AutoSize

# Test API responses
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "API RESPONSE TESTING" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`nTesting Welcome API response..."
try {
    $welcomeResponse = Invoke-RestMethod -Uri "$baseUrl/welcome" -Method GET
    Write-Host "Response: $($welcomeResponse.message)" -ForegroundColor Green
}
catch {
    Write-Host "Failed to get welcome response" -ForegroundColor Red
}

Write-Host "`nTesting Gkach Rate API response..."
try {
    $rateResponse = Invoke-RestMethod -Uri "$baseUrl/api/gkach_rate" -Method GET
    Write-Host "Rate: $($rateResponse.rate) $($rateResponse.currency)" -ForegroundColor Green
}
catch {
    Write-Host "Failed to get rate response" -ForegroundColor Red
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Testing Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
