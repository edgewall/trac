$LocalAppData = $env:LocalAppData
$ProgramData = $env:ProgramData
$workspace = $env:GITHUB_WORKSPACE
$arch = $env:MATRIX_ARCH
$vcpkg_root = $Env:VCPKG_INSTALLATION_ROOT
$vcpkg_downloads = "$LocalAppData\vcpkg\downloads"
$vcpkg_triplet = "$arch-windows"
$vcpkg_dir = "$vcpkg_root\installed\$vcpkg_triplet"
$pyver = $env:MATRIX_PYVER
$svnver = $env:MATRIX_SVNVER
$svndir = "$LocalAppData\subversion-$svnver\$arch"
$svnurl = "https://archive.apache.org/dist/subversion/subversion-$svnver.zip"
$svnarc = "$workspace\subversion-$svnver.zip"
$svnhash = '9D805D79521E994E5F38417705DA5CE4930827C8C4A7A2E9DC81E2F5D1E85A91'
$sqlite_name = 'sqlite-amalgamation-3081101'
$sqlite_url = "https://www.sqlite.org/2015/$sqlite_name.zip"
$sqlite_arc = "$workspace\$sqlite_name.zip"
$sqlite_hash = 'A3B0C07D1398D60AE9D21C2CC7F9BE6B1BC5B0168CD94C321EDE9A0FCE2B3CD7'
$swig_ver = '3.0.12'
$swig_url = "https://prdownloads.sourceforge.net/swig/swigwin-$swig_ver.zip"
$swig_arc = "$workspace\swigwin-$swig_ver.zip"
$swig_hash = "21CE6CBE297A56B697EF6E7E92A83E75CA41DEDC87E48282AB444591986C35F5"
$pydir = "$svndir\python\$pyver"

$venvdir = "$($env:LocalAppData)\venv"
$python = "$($env:pythonLocation)\python.exe"
& $python -m venv $venvdir

$env:PATH = "$svndir\bin;$pydir\bin;$($env:PATH)"
$env:PYTHONPATH = "$pydir\lib;$($env:PYTHONPATH)"

Function Verify-Binary {
    try {
        $svnver_cmd = ((& "$svndir\bin\svn.exe" --version --quiet) `
                       | Out-String).Trim()
    }
    catch {
        $svnver_cmd = ''
        Write-Warning $Error[0]
    }
    if ($svnver_cmd -ne '') {
        Write-Host "Subversion $svnver_cmd"
    }
    else {
        Write-Warning "Subversion unavailable"
    }
    try {
        $cmd = 'import os, svn.core as c; os.write(1, c.SVN_VER_NUMBER)'
        $svnver_py = ((& $python -c $cmd) | Out-String).Trim()
    }
    catch {
        $svnver_py = ''
        Write-Warning $Error[0]
    }
    if ($svnver_py -ne '') {
        Write-Host "Subversion Python bindings $svnver_py"
    }
    else {
        Write-Warning "Subversion Python bindings unavailable"
    }
    return $svnver_cmd -eq $svnver -and $svnver_py -eq $svnver
}

Function Download-File {
    Param([string]$Uri, [string]$OutFile, [string]$Hash)
    Write-Host "Downloading $Uri"
    try {
        if ((Test-Path -Path $OutFile) -and
            ((Get-FileHash $OutFile -Algorithm SHA256).Hash -ne $Hash)
        ) {
            Write-Warning "Remove the restored file due to hash mismatch"
            Remove-Item -Path $OutFile -Force
        }
        if (-not (Test-Path -Path $OutFile)) {
            Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UserAgent curl `
                              -MaximumRetryCount 10 -RetryIntervalSec 5
            if ((Get-FileHash $OutFile -Algorithm SHA256).Hash -ne $Hash) {
                throw "Downloaded file verification failed"
            }
        }
    }
    finally {
        if (Test-Path -Path $OutFile) {
            Get-FileHash $OutFile -Algorithm SHA256 | Format-List
        }
    }
}

if (-not (Verify-Binary)) {
    Write-Host "Building Subversion Python bindings using $svnurl"

    Download-File $svnurl $svnarc $svnhash
    Download-File $sqlite_url $sqlite_arc $sqlite_hash
    Download-File $swig_url $swig_arc $swig_hash
    Expand-Archive -LiteralPath $svnarc -DestinationPath "$workspace"
    Expand-Archive -LiteralPath $sqlite_arc -DestinationPath "$workspace"
    Expand-Archive -LiteralPath $swig_arc -DestinationPath "$workspace"

    Push-Location -LiteralPath $vcpkg_root
    & git pull
    Pop-Location
    $vcpkg_opts = @("--downloads-root=$vcpkg_downloads",
                    "--triplet=$vcpkg_triplet")
    $vcpkg_targets = Get-Content -LiteralPath .github\vcpkg.txt
    & vcpkg $vcpkg_opts update
    & vcpkg $vcpkg_opts install $vcpkg_targets
    if ($LASTEXITCODE) {
        Write-Error "vcpkg install exited with $LASTEXITCODE"
        exit 1
    }

    Set-Location -LiteralPath "$workspace\subversion-$svnver"
    foreach ($patch in 'svn-expat272.patch', 'svn-zlib132.patch') {
        & git apply -v -p0 --whitespace=fix "$workspace\.github\$patch"
    }
    & $python gen-make.py --release `
                          --vsnet-version=2019 `
                          "--with-apr=$vcpkg_dir" `
                          "--with-apr-util=$vcpkg_dir" `
                          "--with-zlib=$vcpkg_dir" `
                          "--with-sqlite=$workspace\$sqlite_name" `
                          "--with-swig=$workspace\swigwin-$swig_ver" `
                          "--with-py3c=$workspace\py3c"
    if ($LASTEXITCODE) {
        Write-Error "gen-make.py exited with $LASTEXITCODE"
        exit 1
    }
    & msbuild subversion_vcnet.sln `
              -nologo -v:q -m -fl `
              "-t:__ALL__:Rebuild;__SWIG_PYTHON__:Rebuild" `
              "-p:Configuration=Release;Platform=$arch"
    if ($LASTEXITCODE) {
        Write-Error "msbuild subversion_vcnet.sln exited with $LASTEXITCODE"
        exit 1
    }

    $deps = @("$vcpkg_dir\bin\libapr*.dll",
              "$vcpkg_dir\bin\apr_*.dll",
              "$vcpkg_dir\bin\libcrypto-*.dll",
              "$vcpkg_dir\bin\libexpat.dll",
              "$vcpkg_dir\bin\libssl-*.dll",
              "$vcpkg_dir\bin\z*.dll")
    Copy-Item -Path $deps -Destination Release

    New-Item -Force -ItemType Directory -Path "$svndir\bin"
    Copy-Item -Path $deps -Destination "$svndir\bin" -Verbose
    Copy-Item -Path @('Release\subversion\svn*\*.exe',
                      'Release\subversion\libsvn_*\*.dll') `
              -Destination "$svndir\bin" `
              -Verbose
    New-Item -Force -ItemType Directory `
             -Path @("$pydir\bin", "$pydir\lib\svn", "$pydir\lib\libsvn")
    $swig_python = 'subversion\bindings\swig\python'
    Copy-Item -Path "Release\$swig_python\libsvn_swig_py\*.dll" `
              -Destination "$pydir\bin" `
              -Verbose
    Copy-Item -Path "$swig_python\svn\*.py" `
              -Destination "$pydir\lib\svn" `
              -Verbose
    Copy-Item -Path @("$swig_python\*.py", "Release\$swig_python\_*.pyd") `
              -Destination "$pydir\lib\libsvn" `
              -Verbose
    & $python -m compileall "$pydir\lib"

    if (-not (Verify-Binary)) {
        exit 1
    }
    Set-Location -LiteralPath $workspace
}
