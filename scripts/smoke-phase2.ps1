# Phase 2 smoke test. Run from the repository root:
#
#   powershell -ExecutionPolicy Bypass -File scripts\smoke-phase2.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\smoke-phase2.ps1 -WsSeconds 0   # skip the socket
#
# It assumes:
#   * Django migrations applied  (backend\django: python manage.py migrate)
#   * FastAPI running on 127.0.0.1:8001
# and it prints what it is checking after each call.
#
# Written for Windows PowerShell 5.1 as well as PowerShell 7: `-SkipHttpErrorCheck`
# does not exist in 5.1, so every call goes through Show-Response, which treats a
# WebException's HTTP status as a normal result (401/422 are the expected answers
# in several of these steps).

param(
    [int]$WsSeconds = 10,
    [string]$OutFile = ""
)

$base = "http://127.0.0.1:8001"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$work = Join-Path $repoRoot ".smoke"
if (-not (Test-Path $work)) { New-Item -ItemType Directory -Path $work | Out-Null }

# Tee every line to a file as well as the console, so a caller that cannot read
# the script's stdout still gets the whole transcript.
function Write-Log {
    param([string]$Message, [string]$Colour)
    Write-Host $Message -ForegroundColor $Colour
    if ($script:OutFile) { Add-Content -Path $script:OutFile -Value $Message }
}

function Show-Response {
    param([string]$Label, $Response, $ErrorRecord)
    if ($ErrorRecord) {
        $webResponse = $ErrorRecord.Exception.Response
        if ($webResponse) {
            $reader = New-Object System.IO.StreamReader($webResponse.GetResponseStream())
            $body = $reader.ReadToEnd()
            $code = [int]$webResponse.StatusCode
        } else {
            $body = $ErrorRecord.Exception.Message
            $code = "no response"
        }
    } else {
        $code = [int]$Response.StatusCode
        $body = $Response.Content
    }
    Write-Log "$Label -> $code $body"
}

function Call-Api {
    param([string]$Label, [string]$Uri, [string]$Method = "Get", [string]$Body, [string]$Token)
    $params = @{ Uri = $Uri; Method = $Method; UseBasicParsing = $true }
    if ($Body) { $params["Body"] = $Body; $params["ContentType"] = "application/json" }
    if ($Token) { $params["Headers"] = @{ Authorization = "Bearer $Token" } }
    try {
        $response = Invoke-WebRequest @params
        Show-Response -Label $Label -Response $response
    } catch {
        Show-Response -Label $Label -ErrorRecord $_
    }
}

Write-Log "== 1. mint a real device token and session in Django ==" "Cyan"
$python = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
$mintScript = Join-Path $repoRoot "backend\django\scripts\mint_run.py"
$mintFile = Join-Path $work "mint.txt"
Remove-Item $mintFile -ErrorAction SilentlyContinue

# The mint script writes its values to a file: a child process' piped stdout
# cannot be captured in every environment, a file always works. Everything is run
# through `cmd /c "..."` because the repository path contains a space, and
# `Start-Process -FilePath` splits it.
$mintCommand = "`"$python`" `"$mintScript`""
cmd /c "set MINT_OUT=$mintFile&& $mintCommand" | Out-Null
if (-not (Test-Path $mintFile)) { throw "mint script produced no values" }

$values = @{}
foreach ($line in (Get-Content $mintFile)) {
    if ($line -match "^([A-Z_]+)=(.+)$") { $values[$Matches[1]] = $Matches[2] }
}
$deviceToken = $values["DEVICE_TOKEN"]
$sessionId = $values["SESSION_ID"]
$userToken = $values["USER_TOKEN"]
$patientId = $values["PATIENT_ID"]
if (-not $deviceToken) { throw "could not mint a device token: $((Get-Content $mintFile) -join ' | ')" }
Write-Log "session $sessionId"

# The device id is inside the device token; decode it rather than guess.
$payload = $deviceToken.Split('.')[1].Replace('-', '+').Replace('_', '/')
switch ($payload.Length % 4) { 2 { $payload += '==' } 3 { $payload += '=' } }
$deviceId = ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload)) | ConvertFrom-Json).device_id

Write-Log "`n== 2. register the session with FastAPI (Django does this on create) ==" "Cyan"
$body = @{ session_id = $sessionId; patient_id = [int]$patientId; device_id = $deviceId; doctor_ids = @(); status = "active" } | ConvertTo-Json
Call-Api -Label "POST /internal/sessions" -Uri "$base/internal/sessions" -Method Post -Body $body -Token $userToken

Write-Log "`n== 3. connect the device (heartbeat) ==" "Cyan"
Call-Api -Label "POST /sensor/connect" -Uri "$base/sensor/connect" -Method Post -Body '{"firmware_version":"smoke-1.0"}' -Token $deviceToken

Write-Log "`n== 4. store a temperature reading (expect 200, stored=true) ==" "Cyan"
$reading = @{ session_id = $sessionId; sensor_type = "temperature"; value = 36.8; unit = "celsius" } | ConvertTo-Json
Call-Api -Label "POST /sensor/data" -Uri "$base/sensor/data" -Method Post -Body $reading -Token $deviceToken

Write-Log "`n== 5. the same reading twice (expect stored=false, duplicate=true) ==" "Cyan"
$withTime = @{ session_id = $sessionId; sensor_type = "temperature"; value = 36.8; unit = "celsius"; recorded_at = "2026-10-05T12:00:00Z" } | ConvertTo-Json
Call-Api -Label "1st POST /sensor/data" -Uri "$base/sensor/data" -Method Post -Body $withTime -Token $deviceToken
Call-Api -Label "2nd POST /sensor/data" -Uri "$base/sensor/data" -Method Post -Body $withTime -Token $deviceToken

Write-Log "`n== 6. a bad token (expect 401) ==" "Cyan"
Call-Api -Label "POST /sensor/data (bad token)" -Uri "$base/sensor/data" -Method Post -Body $reading -Token "not.a.real.token"

Write-Log "`n== 7. an out-of-range value (expect 422) ==" "Cyan"
$bad = @{ session_id = $sessionId; sensor_type = "temperature"; value = 99.0; unit = "celsius" } | ConvertTo-Json
Call-Api -Label "POST /sensor/data (99 C)" -Uri "$base/sensor/data" -Method Post -Body $bad -Token $deviceToken

Write-Log "`n== 8. the same ECG chunk twice (expect duplicate=true, one row) ==" "Cyan"
$chunk = @{ session_id = $sessionId; chunk_index = 0; start_time = "2026-10-05T12:00:00Z"; sample_rate_hz = 250; samples = @(0.1, 0.2, 0.3, 0.4) } | ConvertTo-Json
Call-Api -Label "1st POST /sensor/ecg" -Uri "$base/sensor/ecg" -Method Post -Body $chunk -Token $deviceToken
Call-Api -Label "2nd POST /sensor/ecg" -Uri "$base/sensor/ecg" -Method Post -Body $chunk -Token $deviceToken

Write-Log "`n== 9. read the readings back as a user token (expect 200) ==" "Cyan"
Call-Api -Label "GET /sessions/<id>/readings" -Uri "$base/sessions/$sessionId/readings" -Token $userToken

Write-Log "`n== 10. live WebSocket frame ==" "Cyan"
$wsScript = Join-Path $repoRoot "backend\fastapi\scripts\ws_watch.py"
$fastapiPython = Join-Path $repoRoot "backend\fastapi\.venv\Scripts\python.exe"
if ($WsSeconds -gt 0) {
    $wsLog = Join-Path $work "websocket.txt"
    $wsCommand = "`"$fastapiPython`" `"$wsScript`" $sessionId $userToken $deviceToken $WsSeconds"
    cmd /c "$wsCommand > `"$wsLog`" 2>&1"
    Get-Content $wsLog -ErrorAction SilentlyContinue | ForEach-Object { Write-Log $_ }
} else {
    Write-Log "(skipped: -WsSeconds 0)"
}
