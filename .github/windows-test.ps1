$venvdir = "$($env:LocalAppData)\venv"
& python -m venv $venvdir
& "$venvdir\scripts\activate.ps1"
$python = "$venvdir\scripts\python.exe"
& $python -m pip install --upgrade pip setuptools
& $python -m pip install -r .github\requirements.txt
& $python -m pip list --format=freeze

& choco install -y --no-progress html-tidy
Get-ChildItem -Path "$($env:ProgramData)\chocolatey\lib\html-tidy\tools" `
              -Filter '*.dll' -Recurse `
| Copy-Item -Destination "$venvdir\scripts" -Verbose

$LocalAppData = $env:LocalAppData
$arch = $env:MATRIX_ARCH
$pyver = $env:MATRIX_PYVER
$svnver = $env:MATRIX_SVNVER
$svndir = "$LocalAppData\subversion-$svnver\$arch"
$pydir = "$svndir\python\$pyver"
$venvdir = "$LocalAppData\venv"
$env:PATH = "$svndir\bin;$pydir\bin;$($env:PATH)"
$env:PYTHONPATH = "$pydir\lib;$($env:PYTHONPATH)"

switch -Exact ($env:MATRIX_TRACDB) {
    '' {
        $tracdb_uri = ''
    }
    'sqlite' {
        $tracdb_uri = 'sqlite:db/trac.db'
    }
    'postgresql' {
        $service = Get-Service -Name "postgresql-x64-*"
        $service | Set-Service -StartupType Manual
        $service | Start-Service
        $env:PATH = "$($env:PGBIN);$($env:PATH)"
        $env:PGPASSWORD = 'root'
        & psql -U postgres -c "CREATE USER tracuser NOSUPERUSER NOCREATEDB CREATEROLE PASSWORD 'password'"
        & createdb -U postgres -O tracuser trac
        $tracdb_uri = 'postgres://tracuser:password@localhost/trac?schema=tractest'
        Copy-Item -Path "$($env:PGBIN)\lib*.dll" `
                  -Destination "$venvdir\lib\site-packages\psycopg2" `
                  -Verbose
    }
    'mysql' {
        & choco install -y --no-progress mysql
        & mysql -u root -v -e "CREATE DATABASE trac DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin"
        & mysql -u root -v -e "CREATE USER tracuser@localhost IDENTIFIED BY 'password'"
        & mysql -u root -v -e "GRANT ALL ON trac.* TO tracuser@localhost; FLUSH PRIVILEGES"
        $tracdb_uri = 'mysql://tracuser:password@localhost/trac?charset=utf8mb4'
    }
}

$env:PYTHONWARNINGS = 'default'
Set-Content -Path Makefile.cfg ".uri = $tracdb_uri"
& make.exe status Trac.egg-info compile
if ($LASTEXITCODE) {
    Write-Error "'make.exe status Trac.egg-info compile' exited with $LASTEXITCODE"
    exit 1
}
$rc = 0
& make.exe unit-test
if ($LASTEXITCODE) {
    Write-Warning "'make.exe unit-test' exited with $LASTEXITCODE"
    $rc = 1
}
if ($env:MATRIX_TESTS -eq 'functional') {
    & make.exe functional-test testopts=-v
    if ($LASTEXITCODE) {
        Write-Warning "'make.exe functional-test testopts=-v' exited with $LASTEXITCODE"
        $rc = 1
    }
}
exit $rc
