param(
  [string]$SetupExe,
  [int]$ApiPort = 8001,
  [int]$FrontendPort = 3001
)

$ErrorActionPreference = "Stop"
$InstallDir = Join-Path $env:ProgramFiles "TodoistAssistant"
$DataDir = Join-Path $env:ProgramData "Todometry"

# Pass criteria:
# - setup.exe exits 0/3010/1641 for install and uninstall
# - todometry.exe launches headlessly and API health returns 200
# - frontend responds (any HTTP status)
# - uninstall removes InstallDir and preserves ProgramData by default

function Get-HttpStatus {
  param([string]$Uri, [int]$TimeoutSec = 5)
  try {
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.UseProxy = $false
    $handler.Proxy = $null
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSec)
    $response = $client.GetAsync($Uri).GetAwaiter().GetResult()
    $status = [int]$response.StatusCode
    $response.Dispose()
    $client.Dispose()
    return $status
  } catch {
    try {
      $resp = Invoke-WebRequest -Uri $Uri -Method Get -UseBasicParsing -TimeoutSec $TimeoutSec -Proxy $null
      if ($resp -and $resp.StatusCode) { return [int]$resp.StatusCode }
    } catch {
      if ($_.Exception -and $_.Exception.Response -and $_.Exception.Response.StatusCode) {
        return [int]$_.Exception.Response.StatusCode
      }
    }
    return $null
  }
}

function Wait-Http {
  param([string]$Uri, [int]$TimeoutSec = 60)
  $start = Get-Date
  while (((Get-Date) - $start).TotalSeconds -lt $TimeoutSec) {
    $status = Get-HttpStatus -Uri $Uri -TimeoutSec 5
    if ($status -ne $null) { return $status }
    Start-Sleep -Milliseconds 500
  }
  return $null
}

$allowed = @(0, 3010, 1641)
$logDir = Join-Path $env:TEMP ("todometry-installer-logs-" + [guid]::NewGuid().ToString("N"))
if (-not (Test-Path $logDir)) {
  New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$installLog = Join-Path $logDir "setup-install.log"
$uninstallLog = Join-Path $logDir "setup-uninstall.log"

if (-not $SetupExe) {
  $candidate = Join-Path $PSScriptRoot "..\\..\\dist\\windows\\TodometrySetup.exe"
  if (Test-Path $candidate) {
    $SetupExe = (Resolve-Path $candidate).Path
  }
}
if (-not $SetupExe -or -not (Test-Path $SetupExe)) {
  throw "Setup.exe not found. Provide -SetupExe or build dist/windows/TodometrySetup.exe"
}

if ((Test-Path $InstallDir) -and (Get-ChildItem -LiteralPath $InstallDir -Force | Select-Object -First 1)) {
  throw "Install directory is not empty: $InstallDir. Use a clean runner."
}
$runtimeData = Join-Path $env:TEMP ("todometry-runtime-smoke-" + [guid]::NewGuid().ToString("N"))

Write-Host "Installing: $SetupExe"
$installArgs = @(
  "/install",
  "/quiet",
  "/norestart",
  "/log",
  "`"$installLog`""
)
$install = Start-Process -FilePath $SetupExe -ArgumentList $installArgs -Wait -PassThru
if ($allowed -notcontains $install.ExitCode) {
  throw "setup.exe install failed with code $($install.ExitCode)"
}

$exe = Join-Path $InstallDir "todometry.exe"
if (-not (Test-Path $exe)) {
  throw "Installed executable not found at $exe"
}

$stdoutLog = Join-Path $env:TEMP "todometry-stdout.log"
$stderrLog = Join-Path $env:TEMP "todometry-stderr.log"
$runArgs = "--api-host 127.0.0.1 --api-port $ApiPort --frontend-host 127.0.0.1 --frontend-port $FrontendPort --no-browser --data-dir `"$runtimeData`""
Write-Host "Launching app: $exe $runArgs"
$appProc = Start-Process -FilePath $exe -ArgumentList $runArgs -PassThru -NoNewWindow -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

try {
  $apiStatus = Wait-Http -Uri "http://127.0.0.1:$ApiPort/api/health" -TimeoutSec 60
  if ($apiStatus -ne 200) {
    if (Test-Path $stdoutLog) { Get-Content $stdoutLog -Tail 200 }
    if (Test-Path $stderrLog) { Get-Content $stderrLog -Tail 200 }
    throw "API health check failed (status: $apiStatus)"
  }

  $frontendStatus = Wait-Http -Uri "http://127.0.0.1:$FrontendPort/" -TimeoutSec 60
  if ($frontendStatus -eq $null) {
    if (Test-Path $stdoutLog) { Get-Content $stdoutLog -Tail 200 }
    if (Test-Path $stderrLog) { Get-Content $stderrLog -Tail 200 }
    throw "Frontend check failed"
  }
} finally {
  if ($appProc -and -not $appProc.HasExited) {
    & taskkill /PID $appProc.Id /T /F | Out-Null
    Start-Sleep -Seconds 2
  }
}

Write-Host "Uninstalling..."
$uninstallArgs = @(
  "/uninstall",
  "/quiet",
  "/norestart",
  "/log",
  "`"$uninstallLog`""
)
$uninstall = Start-Process -FilePath $SetupExe -ArgumentList $uninstallArgs -Wait -PassThru
if ($allowed -notcontains $uninstall.ExitCode) {
  throw "setup.exe uninstall failed with code $($uninstall.ExitCode)"
}

if (Test-Path $InstallDir) {
  throw "Install dir still exists after uninstall: $InstallDir"
}
if (-not (Test-Path $DataDir)) {
  throw "Expected ProgramData to be preserved by default, but $DataDir is missing"
}

Write-Host "Smoke test completed successfully."
