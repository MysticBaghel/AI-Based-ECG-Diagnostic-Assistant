# Phase 3 smoke test. Run from the repository root:
#
#   powershell -ExecutionPolicy Bypass -File scripts\smoke-phase3.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\smoke-phase3.ps1 -Duration 10 -SkipEdgeCases
#
# It assumes:
#   * Django migrations applied  (backend\django: python manage.py migrate)
#   * FastAPI running on 127.0.0.1:8001
#   * simulator\.venv created     (see simulator\requirements-dev.txt)
# and it prints what it is checking after every step.
#
# What it proves, in order:
#   1. mint a real device token + active session in Django
#   2. register that session with FastAPI (Django does this on create)
#   3. run the simulator with every edge-case flag on, and check that the
#      deliberate chunk gap and the deliberate re-send both behaved
#   4. run the simulator normally for -Duration seconds
#   5. count the rows in the telemetry database: one per sensor type, plus the
#      ECG chunks - which is the statement "the simulator fills the DB"
#
# Written for Windows PowerShell 5.1 as well as PowerShell 7, like its Phase 2
# sibling. Every value travels through files rather than piped child stdout,
# because the repository path contains spaces.

param(
    [string]$BaseUrl = "http://127.0.0.1:8001",
    [int]$Duration = 30,
    [double]$Interval = 1.0,
    [int]$EdgeCaseSeconds = 12,
    [switch]$SkipEdgeCases,
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$work = Join-Path $repoRoot ".smoke"
if (-not (Test-Path $work)) { New-Item -ItemType Directory -Path $work | Out-Null }

$simPython = Join-Path $repoRoot "simulator\.venv\Scripts\python.exe"
$djangoPython = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
$mintScript = Join-Path $repoRoot "backend\django\scripts\mint_new_run.py"
$mintFile = Join-Path $work "mint.txt"
$dbFile = Join-Path $repoRoot "backend\fastapi\fastapi-dev.sqlite3"
$summaryFile = Join-Path $work "simulator-summary.json"
$edgeSummaryFile = Join-Path $work "simulator-edge-summary.json"
$countsFile = Join-Path $work "row-counts.json"
$transcript = if ($OutFile) { $OutFile } else { Join-Path $work "smoke-phase3.txt" }

# Tee every line to a file as well as the console, so a caller that cannot read
# this script's stdout still gets the whole transcript.
function Write-Log {
    param([string]$Message, [string]$Colour = "Gray")
    Write-Host $Message -ForegroundColor $Colour
    Add-Content -Path $transcript -Value $Message
}

function Fail {
    param([string]$Message)
    Write-Log "FAILED: $Message" "Red"
    exit 1
}

if (-not (Test-Path $simPython)) { Fail "no simulator venv at $simPython - see simulator\requirements-dev.txt" }
if (-not (Test-Path $djangoPython)) { Fail "no Django venv at $djangoPython" }

Write-Log "== 0. the service is up ==" "Cyan"
try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/health" -TimeoutSec 5
    Write-Log "GET /health -> $($health | ConvertTo-Json -Compress)"
} catch {
    Fail "FastAPI is not answering on $BaseUrl ($_)"
}

Write-Log "`n== 1. mint a real device token and a FRESH session in Django ==" "Cyan"
Remove-Item $mintFile -ErrorAction SilentlyContinue
# The mint script writes to a file: a child process' piped stdout cannot be
# captured in every environment, a file always works. The output path travels in
# an environment variable (MINT_OUT) rather than as an argument, because a path
# containing spaces survives an environment variable in every shell.
$env:MINT_OUT = $mintFile
& $djangoPython $mintScript
if (-not (Test-Path $mintFile)) { Fail "the mint script produced no values" }

$values = @{}
foreach ($line in (Get-Content $mintFile)) {
    if ($line -match "^([A-Z_]+)=(.+)$") { $values[$Matches[1]] = $Matches[2] }
}
$deviceToken = $values["DEVICE_TOKEN"]
$sessionId = $values["SESSION_ID"]
$userToken = $values["USER_TOKEN"]
$patientId = $values["PATIENT_ID"]
$deviceId = $values["DEVICE_ID"]
if (-not $deviceToken -or -not $sessionId) { Fail "could not mint a token: $((Get-Content $mintFile) -join ' | ')" }
Write-Log "session   $sessionId"
Write-Log "device    $deviceId"
Write-Log "patient   $patientId"

Write-Log "`n== 2. register the session with FastAPI (Django does this on create) ==" "Cyan"
$body = @{
    session_id = $sessionId
    patient_id = [int]$patientId
    device_id  = $deviceId
    doctor_ids = @()
    status     = "active"
} | ConvertTo-Json
try {
    $registered = Invoke-RestMethod -Uri "$BaseUrl/internal/sessions" -Method Post -Body $body `
        -ContentType "application/json" -Headers @{ Authorization = "Bearer $userToken" }
    Write-Log "POST /internal/sessions -> $($registered | ConvertTo-Json -Compress)"
} catch {
    Fail "could not register the session (is the minted USER_TOKEN an admin token?): $_"
}

if (-not $SkipEdgeCases) {
    Write-Log "`n== 3. edge cases: drop 30% of the chunks, re-send every chunk, go offline early ==" "Cyan"
    $edgeArgs = @(
        "-m", "simulator",
        "--base-url", $BaseUrl,
        "--device-token", $deviceToken,
        "--session-id", $sessionId,
        "--duration", "$EdgeCaseSeconds",
        "--interval", "0.5",
        "--ecg", "--ecg-source", "synthetic",
        "--noise",
        "--drop-chunks", "0.3",
        "--resend-chunks", "1.0",
        "--offline-after", "$EdgeCaseSeconds",
        "--seed", "20261006",
        "--output-json", $edgeSummaryFile
    )
    Push-Location $repoRoot
    try { & $simPython @edgeArgs } finally { Pop-Location }
    if (-not (Test-Path $edgeSummaryFile)) { Fail "the edge-case run wrote no summary" }

    $edge = Get-Content $edgeSummaryFile -Raw | ConvertFrom-Json
    Write-Log ("edge summary: chunks produced {0}, sent {1}, accepted {2}, duplicates {3}, dropped {4}, re-sent {5}" -f `
        $edge.ecg.chunks_produced, $edge.ecg.chunks_sent, $edge.ecg.chunks_stored, `
        $edge.ecg.chunks_duplicate, $edge.ecg.chunks_dropped, $edge.ecg.chunks_resent)

    if ($edge.ecg.chunks_dropped -lt 1) { Fail "--drop-chunks did not drop anything" }
    if ($edge.ecg.chunks_resent -lt 1) { Fail "--resend-chunks did not re-send anything" }
    if ($edge.ecg.chunks_duplicate -ne $edge.ecg.chunks_resent) {
        Fail "a re-sent chunk was not answered with duplicate=true ($($edge.ecg.chunks_duplicate) vs $($edge.ecg.chunks_resent))"
    }
    if ($edge.ecg.chunks_unique_stored -ne ($edge.ecg.chunks_stored - $edge.ecg.chunks_resent)) {
        Fail "the idempotency arithmetic in the summary does not add up"
    }
    Write-Log "edge cases OK: a chunk was skipped, a chunk was re-sent, and the re-send stored nothing" "Green"
}

Write-Log "`n== 4. the real run: $Duration s, interval $Interval s, MIT-BIH ECG ==" "Cyan"
$simArgs = @(
    "-m", "simulator",
    "--base-url", $BaseUrl,
    "--device-token", $deviceToken,
    "--session-id", $sessionId,
    "--duration", "$Duration",
    "--interval", "$Interval",
    "--ecg",
    "--output-json", $summaryFile
)
Push-Location $repoRoot
try { & $simPython @simArgs } finally { Pop-Location }
if (-not (Test-Path $summaryFile)) { Fail "the simulator wrote no summary" }

$summary = Get-Content $summaryFile -Raw | ConvertFrom-Json
Write-Log ("simulator summary: readings stored {0} ({1}); ECG chunks stored {2}, duplicates {3}, failed {4}" -f `
    $summary.readings_total.stored, `
    (($summary.readings.PSObject.Properties | ForEach-Object { "$($_.Name)=$($_.Value.stored)" }) -join ", "), `
    $summary.ecg.chunks_stored, $summary.ecg.chunks_duplicate, $summary.ecg.chunks_failed)

if ($summary.readings_total.stored -lt 4) { Fail "fewer than four readings were stored" }
if ($summary.ecg.chunks_stored -lt 1) { Fail "no ECG chunks were stored" }

Write-Log "`n== 5. what is actually in the database ==" "Cyan"
# Read the same SQLite file the service is using. Read-only, so it works while
# the server holds the file open. (PostgreSQL: the same SQL, pointed at the
# telemetry schema - see docs/phase-3-smoke-test.md.)
$countScript = @'
import json, os, sqlite3, sys

db, session_id, out = sys.argv[1], sys.argv[2], sys.argv[3]
# SQLite stores a UUID as 32 hex characters with no dashes.
key = session_id.replace("-", "").lower()
connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
connection.row_factory = sqlite3.Row

readings = {
    row["sensor_type"]: row["n"]
    for row in connection.execute(
        "SELECT sensor_type, COUNT(*) AS n FROM sensor_readings "
        "WHERE session_id = ? GROUP BY sensor_type",
        (key,),
    )
}
ecg = connection.execute(
    "SELECT COUNT(*) AS chunks, COALESCE(SUM(sample_count), 0) AS samples "
    "FROM ecg_chunks WHERE session_id = ?",
    (key,),
).fetchone()

data = {
    "session_id": session_id,
    "sensor_readings": readings,
    "sensor_readings_total": sum(readings.values()),
    "ecg_chunks": ecg["chunks"],
    "ecg_samples": ecg["samples"],
}
with open(out, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2, sort_keys=True)
print(json.dumps(data, sort_keys=True))
'@
$countScriptPath = Join-Path $work "count-rows.py"
Set-Content -Path $countScriptPath -Value $countScript -Encoding UTF8

& $simPython $countScriptPath $dbFile $sessionId $countsFile
if (-not (Test-Path $countsFile)) { Fail "the counting script produced no output" }
$counts = Get-Content $countsFile -Raw | ConvertFrom-Json

Write-Log ""
Write-Log "  session $($counts.session_id)" "White"
Write-Log "  ---- sensor_readings ----" "White"
foreach ($name in @("temperature", "spo2", "pulse", "motion")) {
    $n = 0
    $property = $counts.sensor_readings.PSObject.Properties[$name]
    if ($property) { $n = $property.Value }
    Write-Log ("  {0,-14} {1,6} rows" -f $name, $n)
    if ($n -lt 1) { Fail "no $name rows were stored for this session" }
}
Write-Log ("  {0,-14} {1,6} rows" -f "TOTAL", $counts.sensor_readings_total)
Write-Log "  ---- ecg_chunks ----" "White"
Write-Log ("  {0,-14} {1,6} rows ({2} samples, never one row per sample)" -f "chunks", $counts.ecg_chunks, $counts.ecg_samples)
if ($counts.ecg_chunks -lt 1) { Fail "no ECG chunks were stored for this session" }

Write-Log "`nAll checks passed. Transcript: $transcript" "Green"
Write-Log "Screening aid, not a medical diagnosis."
