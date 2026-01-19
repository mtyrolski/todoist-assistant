param(
    [string]$NodeVersion = "20.11.1"
)

$ErrorActionPreference = "Stop"

function Get-PythonCmd {
    if (Get-Command python3 -ErrorAction SilentlyContinue) {
        return "python3"
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    throw "Python is required to build the installer."
}

function Get-WixBin {
    if ($env:WIX_BIN -and (Test-Path (Join-Path $env:WIX_BIN "candle.exe"))) {
        return $env:WIX_BIN
    }
    if ($env:WIX -and (Test-Path (Join-Path $env:WIX "bin\candle.exe"))) {
        return (Join-Path $env:WIX "bin")
    }
    $candle = Get-Command candle.exe -ErrorAction SilentlyContinue
    if ($candle) {
        return (Split-Path $candle.Path)
    }
    $candidates = @(
        "C:\\Program Files (x86)\\WiX Toolset v3.11\\bin",
        "C:\\Program Files\\WiX Toolset v3.11\\bin"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path (Join-Path $candidate "candle.exe")) {
            return $candidate
        }
    }
    throw "WiX Toolset not found. Install WiX v3.11+ and ensure candle.exe is on PATH."
}

$pythonCmd = Get-PythonCmd
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\\..")
$distRoot = Join-Path $repoRoot "dist\\windows"
$stageRoot = Join-Path $distRoot "stage"
$buildRoot = Join-Path $distRoot "build"
$wixObjRoot = Join-Path $distRoot "wixobj"

Push-Location $repoRoot
try {
    if (Test-Path $distRoot) {
        Remove-Item $distRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $stageRoot | Out-Null
    New-Item -ItemType Directory -Path $buildRoot | Out-Null
    New-Item -ItemType Directory -Path $wixObjRoot | Out-Null

    $version = (& uv run $pythonCmd -m scripts.windows.get_version).Trim()
    if (-not $version) {
        throw "Unable to determine version from pyproject.toml"
    }

    $frontendDir = Join-Path $repoRoot "frontend"
    if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
        npm --prefix $frontendDir install
    }
    $env:NEXT_TELEMETRY_DISABLED = "1"
    npm --prefix $frontendDir run build

    $frontendStage = Join-Path $stageRoot "frontend"
    New-Item -ItemType Directory -Path $frontendStage | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $frontendStage ".next") -Force | Out-Null
    Copy-Item (Join-Path $frontendDir ".next\\standalone\\*") $frontendStage -Recurse -Force
    Copy-Item (Join-Path $frontendDir ".next\\static") (Join-Path $frontendStage ".next\\static") -Recurse -Force
    Copy-Item (Join-Path $frontendDir "public") (Join-Path $frontendStage "public") -Recurse -Force

    $configStage = Join-Path $stageRoot "config"
    New-Item -ItemType Directory -Path $configStage | Out-Null
    Copy-Item (Join-Path $repoRoot "configs\\*") $configStage -Recurse -Force
    Copy-Item (Join-Path $repoRoot ".env.example") (Join-Path $configStage ".env.example") -Force

    $specPath = Join-Path $repoRoot "scripts\\windows\\pyinstaller\\todoist-assistant.spec"
    $pyDist = Join-Path $distRoot "pyinstaller"
    & uv run $pythonCmd -m PyInstaller --noconfirm --clean --distpath $pyDist --workpath $buildRoot $specPath

    $appStage = Join-Path $stageRoot "app"
    New-Item -ItemType Directory -Path $appStage | Out-Null
    Copy-Item (Join-Path $pyDist "todoist-assistant.exe") $appStage -Force

    $nodeZipName = "node-v$NodeVersion-win-x64.zip"
    $nodeZip = Join-Path $distRoot $nodeZipName
    $nodeUrl = "https://nodejs.org/dist/v$NodeVersion/$nodeZipName"
    if (-not (Test-Path $nodeZip)) {
        Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeZip
    }
    $nodeExtract = Join-Path $distRoot "node-v$NodeVersion-win-x64"
    if (Test-Path $nodeExtract) {
        Remove-Item $nodeExtract -Recurse -Force
    }
    Expand-Archive -Path $nodeZip -DestinationPath $distRoot

    $nodeStage = Join-Path $stageRoot "node"
    New-Item -ItemType Directory -Path $nodeStage | Out-Null
    Copy-Item (Join-Path $nodeExtract "*") $nodeStage -Recurse -Force

    $wixBin = Get-WixBin
    $heat = Join-Path $wixBin "heat.exe"
    $candle = Join-Path $wixBin "candle.exe"
    $light = Join-Path $wixBin "light.exe"

    $appWxs = Join-Path $distRoot "app.wxs"
    $frontendWxs = Join-Path $distRoot "frontend.wxs"
    $nodeWxs = Join-Path $distRoot "node.wxs"
    $configWxs = Join-Path $distRoot "config.wxs"
    $mainWxs = Join-Path $repoRoot "scripts\\windows\\wix\\todoist-assistant.wxs"

    & $heat dir $appStage -cg AppFiles -dr INSTALLFOLDER -var var.AppSource -ag -srd -sfrag -out $appWxs
    & $heat dir $frontendStage -cg FrontendFiles -dr FRONTENDDIR -var var.FrontendSource -ag -srd -sfrag -out $frontendWxs
    & $heat dir $nodeStage -cg NodeFiles -dr NODEDIR -var var.NodeSource -ag -srd -sfrag -out $nodeWxs
    & $heat dir $configStage -cg ConfigFiles -dr CONFIGDIR -var var.ConfigSource -ag -srd -sfrag -out $configWxs

    $wixArgs = @(
        "-nologo",
        "-ext", "WixUtilExtension",
        "-ext", "WixUIExtension",
        "-dSourceDir=$repoRoot",
        "-dProductVersion=$version",
        "-dAppSource=$appStage",
        "-dFrontendSource=$frontendStage",
        "-dNodeSource=$nodeStage",
        "-dConfigSource=$configStage",
        "-out", (Join-Path $wixObjRoot ""),
        $mainWxs,
        $appWxs,
        $frontendWxs,
        $nodeWxs,
        $configWxs
    )
    & $candle @wixArgs

    $wixObjFiles = Get-ChildItem -Path $wixObjRoot -Filter "*.wixobj" | Select-Object -ExpandProperty FullName
    $msiPath = Join-Path $distRoot ("todoist-assistant-$version.msi")
    & $light -nologo -ext WixUtilExtension -ext WixUIExtension -out $msiPath @wixObjFiles

    Write-Host "MSI created: $msiPath"
} finally {
    Pop-Location
}
