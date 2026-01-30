param(
  [string]$MsiPath,
  [string]$SetupPath,
  [string]$DistRoot = "dist\\windows"
)

$ErrorActionPreference = "Stop"

$certPath = $env:WINDOWS_SIGNING_CERTIFICATE
$certPassword = $env:WINDOWS_SIGNING_CERTIFICATE_PASSWORD
if (-not $certPath -or -not $certPassword) {
  throw "WINDOWS_SIGNING_CERTIFICATE and WINDOWS_SIGNING_CERTIFICATE_PASSWORD must be set."
}

$timestampUrl = $env:WINDOWS_SIGNING_TIMESTAMP_URL
if (-not $timestampUrl) {
  $timestampUrl = "http://timestamp.digicert.com"
}

$signtool = $env:WINDOWS_SIGNTOOL_PATH
if (-not $signtool) {
  $signtoolCmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if ($signtoolCmd) {
    $signtool = $signtoolCmd.Path
  }
}
if (-not $signtool) {
  throw "signtool.exe not found. Install the Windows SDK or set WINDOWS_SIGNTOOL_PATH."
}

$targets = @()
if ($MsiPath) {
  $targets += $MsiPath
} else {
  $msiCandidate = Get-ChildItem -Path $DistRoot -Filter "todoist-assistant-*.msi" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($msiCandidate) {
    $targets += $msiCandidate.FullName
  }
}

if ($SetupPath) {
  $targets += $SetupPath
} else {
  $setupCandidate = Join-Path $DistRoot "TodoistAssistantSetup.exe"
  if (Test-Path $setupCandidate) {
    $targets += $setupCandidate
  }
}

if (-not $targets) {
  throw "No artifacts found to sign. Provide -MsiPath/-SetupPath or ensure DistRoot contains the outputs."
}

foreach ($target in $targets) {
  Write-Host "Signing $target"
  & $signtool sign /fd SHA256 /td SHA256 /tr $timestampUrl /f $certPath /p $certPassword /a /as $target
  if ($LASTEXITCODE -ne 0) {
    throw "signtool failed with exit code $LASTEXITCODE"
  }
}
