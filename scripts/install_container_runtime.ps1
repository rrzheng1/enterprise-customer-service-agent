# System installation only; run after the user authorizes Docker/WSL installation.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"'
    $installer = Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList $arguments -PassThru -Wait
    exit $installer.ExitCode
}
Start-Transcript -Path (Join-Path $projectRoot 'data\container-install.log') -Append
try {
    # Do not reboot the machine automatically.
    & dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
    if ($LASTEXITCODE -notin @(0, 3010)) { throw "VirtualMachinePlatform failed: $LASTEXITCODE" }
    & dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
    if ($LASTEXITCODE -notin @(0, 3010)) { throw "WSL optional feature failed: $LASTEXITCODE" }
    & winget.exe install --id Microsoft.WSL --exact --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) { throw "WSL package installation failed: $LASTEXITCODE" }
    & winget.exe install --id Docker.DockerDesktop --exact --force --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0 -and -not (Test-Path "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe")) {
        throw "Docker installation failed: $LASTEXITCODE"
    }
    Write-Output 'Installation finished. A Windows restart may be needed; it was not requested automatically.'
} finally {
    Stop-Transcript
}
