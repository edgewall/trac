@ECHO OFF
::
:: Trac post-commit-hook script for Windows
::
:: Contributed by markus, modified by cboos.

:: Usage:
::
:: 1) Insert the following line in your post-commit.bat script
::
:: call %~dp0\trac-post-commit-hook.cmd %1 %2
::
:: 2) Check the 'Modify paths' section below, be sure to set at least TRAC_ENV


:: ----------------------------------------------------------
:: Modify paths here:

:: -- this one *must* be set
SET TRAC_ENV=

:: -- set if Python is not in the system path
SET PYTHON_PATH=

:: -- set to the folder containing trac/ if installed in a non-standard location
SET TRAC_PATH=
:: ----------------------------------------------------------

:: Do not execute hook if trac environment does not exist
IF NOT EXIST %TRAC_ENV% GOTO :EOF

set PATH=%PYTHON_PATH%;%PATH%
set PYTHONPATH=%TRAC_PATH%;%PYTHONPATH%

SET REV=%2

Python "%~dp0\trac-post-commit-hook" -p "%TRAC_ENV%" -r "%REV%" 

