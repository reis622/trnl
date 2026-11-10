# trnl installer / updater for Windows (PowerShell 5.1+). ASCII only on purpose.
#   PowerShell:  irm https://raw.githubusercontent.com/reis622/trnl/main/install.ps1 | iex
#   cmd:         powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/reis622/trnl/main/install.ps1 | iex"
# Creates %USERPROFILE%\trnl\venv, installs trnl (latest GitHub release wheel), copies trnl.exe to
# %USERPROFILE%\bin and puts that on the user PATH. Running it again updates an existing install.
# Offline language packs are NOT downloaded here (later, on demand: trnl -s).
& {
$ErrorActionPreference = 'Stop'
$Repo = 'reis622/trnl'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }

$root = Join-Path $env:USERPROFILE 'trnl'
$venv = Join-Path $root 'venv'
$bin  = Join-Path $env:USERPROFILE 'bin'
# a local wheel next to this script (zip / trnl-setup.bat way); empty when piped through iex
$here = $PSScriptRoot

function Test-Py($exe, $extra) {
    try {
        $v = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v -match '^3\.(\d+)$' -and [int]$Matches[1] -ge 9) { return $true }
    } catch { }
    return $false
}

function Find-Python {
    foreach ($ver in @('-3.12', '-3.13', '-3.11', '-3.10', '-3')) {
        if ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-Py 'py' @($ver))) { return ,@('py', $ver) }
    }
    foreach ($p in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                     "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
                     "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
                     "$env:ProgramFiles\Python312\python.exe",
                     "$env:ProgramFiles\Python313\python.exe")) {
        if ((Test-Path $p) -and (Test-Py $p @())) { return ,@($p) }
    }
    # 'python' may be the Microsoft Store stub; Test-Py rejects it
    if ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Py 'python' @())) { return ,@('python') }
    return $null
}

function Get-Package {
    # 1) local wheel next to the script  2) latest GitHub release wheel  3) source zip of the main branch
    if ($here) {
        $w = Get-ChildItem -Path $here -Filter 'trnl-*.whl' -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
        if ($w) { return $w.FullName }
    }
    try {
        $rel = Invoke-RestMethod -UseBasicParsing -Headers @{ 'User-Agent' = 'trnl-installer' } "https://api.github.com/repos/$Repo/releases/latest"
        $asset = $rel.assets | Where-Object { $_.name -match '^trnl-\d[^-]*-py3-none-any\.whl$' } | Select-Object -First 1
        if ($asset) {
            $out = Join-Path $env:TEMP $asset.name
            Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $out
            return $out
        }
    } catch {
        Write-Host "GitHub release okunamadi ($($_.Exception.Message)), kaynak koddan kuruluyor..."
    }
    return "https://github.com/$Repo/archive/refs/heads/main.zip"
}

$py = Find-Python
if (-not $py) {
    Write-Host 'Python 3.9+ bulunamadi. winget ile Python 3.12 kuruluyor...'
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
        $py = Find-Python
    }
    if (-not $py) {
        Write-Host 'Python kurulamadi. https://www.python.org/downloads/ adresinden Python 3.12 kur'
        Write-Host '("Add python.exe to PATH" kutusunu isaretle), sonra bu komutu tekrar calistir.'
        return
    }
}
$pyExe = $py[0]; $pyArgs = @(); if ($py.Count -gt 1) { $pyArgs = $py[1..($py.Count - 1)] }

New-Item -ItemType Directory -Force -Path $root, $bin | Out-Null
$vpy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $vpy)) {
    Write-Host 'venv olusturuluyor...'
    & $pyExe @pyArgs -m venv $venv
    if ($LASTEXITCODE -ne 0) { Write-Host 'venv olusturulamadi.'; return }
}
& $vpy -m pip install --disable-pip-version-check -q --upgrade pip
$pkg = Get-Package
Write-Host "trnl kuruluyor ($pkg)..."
& $vpy -m pip install --disable-pip-version-check -q --upgrade $pkg
if ($LASTEXITCODE -ne 0) { Write-Host 'pip install basarisiz.'; return }
# same version number but new files (update): reinstall trnl itself, keep the dependencies
& $vpy -m pip install --disable-pip-version-check -q --force-reinstall --no-deps $pkg
if ($pkg -like "$env:TEMP*") { Remove-Item -LiteralPath $pkg -Force -ErrorAction SilentlyContinue }

# ctranslate2 needs the MSVC++ runtime (msvcp140.dll)
$ctOk = $true
try { & $vpy -c "import ctranslate2" 2>$null; if ($LASTEXITCODE -ne 0) { $ctOk = $false } } catch { $ctOk = $false }
if (-not $ctOk) {
    Write-Host 'Visual C++ runtime eksik, kuruluyor...'
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Microsoft.VCRedist.2015+.x64 --accept-package-agreements --accept-source-agreements
    } else {
        Write-Host 'https://aka.ms/vs/17/release/vc_redist.x64.exe indirip kur.'
    }
}

# trnl.exe goes straight onto PATH (no .bat shim), so quoted text like trnl "a & b" is passed intact.
$exe = Join-Path $venv 'Scripts\trnl.exe'
try {
    Copy-Item -LiteralPath $exe -Destination (Join-Path $bin 'trnl.exe') -Force
} catch {
    Write-Host 'trnl.exe kopyalanamadi: acik bir trnl varsa kapat (Ctrl+C) ve komutu tekrar calistir.'
    return
}
$oldBat = Join-Path $bin 'trnl.bat'
if (Test-Path -LiteralPath $oldBat) { Remove-Item -LiteralPath $oldBat -Force }

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $userPath) { $userPath = '' }
if (($userPath -split ';') -notcontains $bin) {
    [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ';' + $bin).TrimStart(';'), 'User')
    Write-Host "$bin PATH'e eklendi (diger terminalleri yeniden ac)."
}
if (($env:Path -split ';') -notcontains $bin) { $env:Path = $env:Path.TrimEnd(';') + ';' + $bin }

Write-Host ''
Write-Host 'Kurulum tamam. Dene:  trnl hello'
Write-Host 'Internetsiz calismasi icin dil paketlerini istedigin zaman indir:  trnl -s   (sadece en,tr icin: trnl -s en,tr)'
Write-Host 'Not: Metinde & (ampersand) kullanacaksaniz cumleyi cift tirnak icinde yazin: trnl "rock & roll"'
}
