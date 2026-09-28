# jevanced installer for Windows.
#
# Run this in PowerShell:
#
#   irm https://raw.githubusercontent.com/rbourdon/jevanced/main/install.ps1 | iex
#
# It finds Razor Enhanced, downloads the latest jevanced release, and puts it
# in Razor Enhanced's Scripts folder. Run it again to update. Your API key and
# settings live in %APPDATA%\jevanced and are never touched.
#
# To choose the folder yourself, set it first:
#   $env:JEVANCED_RE_DIR = "C:\path\to\RazorEnhanced"

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$ReleaseUrl = "https://github.com/rbourdon/jevanced/releases/latest/download/jevanced.zip"

function Find-RazorEnhanced {
    if ($env:JEVANCED_RE_DIR) {
        if (Test-Path (Join-Path $env:JEVANCED_RE_DIR "RazorEnhanced.exe")) { return $env:JEVANCED_RE_DIR }
        throw "RazorEnhanced.exe isn't in $env:JEVANCED_RE_DIR."
    }

    # A running copy is the surest answer.
    $running = Get-Process -Name "RazorEnhanced" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path } | Select-Object -First 1
    if ($running) { return Split-Path $running.Path }

    # ClassicUO launches Razor Enhanced as a plugin; its profiles name the path.
    $found = @()
    $roots = @(
        "$env:USERPROFILE\Desktop", "$env:USERPROFILE\Documents", "$env:USERPROFILE\Downloads",
        "$env:USERPROFILE\Games", "$env:LOCALAPPDATA", "$env:APPDATA",
        "$env:ProgramFiles", "${env:ProgramFiles(x86)}", "C:\Games", "C:\UO", "C:\"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
    foreach ($root in $roots) {
        $depth = 5
        if ($root -eq "C:\") { $depth = 2 }
        $found += Get-ChildItem -Path $root -Filter "RazorEnhanced.exe" -Recurse -Depth $depth `
            -File -ErrorAction SilentlyContinue | ForEach-Object { $_.DirectoryName }
    }
    $found = $found | Select-Object -Unique
    if ($found.Count -eq 1) { return $found[0] }
    if ($found.Count -gt 1) {
        Write-Host "Found more than one Razor Enhanced:"
        for ($i = 0; $i -lt $found.Count; $i++) { Write-Host ("  [{0}] {1}" -f ($i + 1), $found[$i]) }
        $pick = Read-Host "Which one? (number)"
        return $found[[int]$pick - 1]
    }

    $typed = Read-Host "Couldn't find Razor Enhanced. Paste the folder that has RazorEnhanced.exe"
    $typed = $typed.Trim('"', ' ')
    if (-not (Test-Path (Join-Path $typed "RazorEnhanced.exe"))) { throw "RazorEnhanced.exe isn't in $typed." }
    return $typed
}

$reDir = Find-RazorEnhanced
$scripts = Join-Path $reDir "Scripts"
New-Item -ItemType Directory -Force -Path $scripts | Out-Null
Write-Host "Razor Enhanced: $reDir"

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("jevanced-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
try {
    $zip = Join-Path $tmp "jevanced.zip"
    if ($env:JEVANCED_ZIP) {
        # A zip you already have (offline installs, testing a build).
        Copy-Item $env:JEVANCED_ZIP $zip
    } else {
        Write-Host "Downloading the latest jevanced..."
        Invoke-WebRequest -Uri $ReleaseUrl -OutFile $zip -UseBasicParsing
    }
    $unpacked = Join-Path $tmp "x"
    Expand-Archive -Path $zip -DestinationPath $unpacked -Force

    # Replace the package folder outright so files removed upstream don't linger.
    $pkg = Join-Path $scripts "jevanced"
    if (Test-Path $pkg) { Remove-Item -Recurse -Force $pkg }
    Copy-Item -Recurse -Force (Join-Path $unpacked "jevanced") $pkg
    Copy-Item -Force (Join-Path $unpacked "run_jevanced.py") (Join-Path $scripts "run_jevanced.py")

    $version = (Select-String -Path (Join-Path $pkg "__init__.py") -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
    Write-Host ""
    Write-Host "Installed jevanced $version to $scripts" -ForegroundColor Green
    Write-Host "In Razor Enhanced: Scripting tab > Add > run_jevanced.py > Play."
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
