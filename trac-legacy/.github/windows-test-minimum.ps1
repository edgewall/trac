$venvdir = "$($env:LocalAppData)\venv"
& python -m venv $venvdir
$python = "$venvdir\scripts\python.exe"
& "$venvdir\scripts\activate.ps1"
& $python -m pip install --upgrade pip setuptools
& $python -m pip install -r .github\requirements-minimum.txt
& $python -m pip list --format=freeze

& choco install -y --no-progress html-tidy
Get-ChildItem -Path "$($env:ProgramData)\chocolatey\lib\html-tidy\tools" `
              -Filter '*.dll' -Recurse `
| Copy-Item -Destination "$venvdir\scripts" -Verbose

$env:PYTHONWARNINGS = 'default'
Set-Content -Path Makefile.cfg '.uri ='
& make.exe status Trac.egg-info
if ($LASTEXITCODE) {
    Write-Error "'make.exe status Trac.egg-info' exited with $LASTEXITCODE"
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
