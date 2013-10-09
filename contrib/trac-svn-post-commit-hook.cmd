@ECHO OFF
::
:: Copyright (C) 2007-2013 Edgewall Software
:: Copyright (C) 2007 Markus Tacker <m@tacker.org>
:: Copyright (C) 2007 Christian Boos <cboos@edgewall.org>
:: All rights reserved.
::
:: This software is licensed as described in the file COPYING, which
:: you should have received as part of this distribution. The terms
:: are also available at http://trac.edgewall.com/license.html.
::
:: This software consists of voluntary contributions made by many
:: individuals. For the exact contribution history, see the revision
:: history and logs, available at http://trac.edgewall.org/.
:: Trac post-commit-hook script for Windows
::
:: Modified for the multirepos branch to use the `changeset` command.

:: Usage:
::
:: 1. Insert the following line in your REPOS/hooks/post-commit.bat script:
::
::      call %~dp0\trac-post-commit-hook.cmd %1 %2
::
:: 2. Check the 'Modify paths' section below, be sure to set at least TRAC_ENV
::
:: 3. Verify that the hook is working:
::
::      - enable DEBUG level logging to a file and to the console
::        (see TracLogging)
::
::      - call the trac-post-commit-hook.cmd from a cmd.exe shell:
::
::          trac-post-commit-hook.cmd <REPOS> 123
::
::      - call the post-commit.bat hook from a cmd.exe shell (check that
::        no unwanted side-effects could be triggered when doing this...):
::
::          post-commit.bat <REPOS> 123
::
::      - in each case, verify that you actually see the logging from Trac
::        and in particular that you see something like (near the end):
::
::          DEBUG: Event changeset_added on <REPOS> for revision 123
::


:: ----------------------------------------------------------
:: Modify paths here:

:: -- this one *must* be set
set TRAC_ENV=

:: -- set if Python is not in the system path
set PYTHON_PATH=

:: -- set to the folder containing trac/ if installed in a non-standard location
set TRAC_PATH=
:: ----------------------------------------------------------

:: -- Do not execute hook if trac environment does not exist
if not exist %TRAC_ENV% goto :EOF

:: -- Determine trac-admin

:: By default assume it's reachable from the PATH
set TRAC_ADMIN=trac-admin.exe

:: ... or take it from the Scripts folder of the specified Python installation
if not %PYTHON_PATH%.==. set TRAC_ADMIN="%PYTHON_PATH%/Scripts/trac-admin.exe"

:: ... or take it from the specified Trac source checkout
if not %TRAC_PATH%.==. set TRAC_ADMIN=python.exe "%TRAC_PATH%/trac/admin/console.py"

:: -- Setup the environment
set PATH=%PYTHON_PATH%;%PATH%
set PYTHONPATH=%TRAC_PATH%;%PYTHONPATH%

:: -- Retrieve the information that Subversion gave to the hook
set REPOS=%1
set REV=%2

:: Now we're about to call trac-admin's changeset added command.
:: We have to call it like that:
::
::   repository changeset added <repos> <rev>
::
:: where <repos> can be the repository symbolic name or directly
:: the repository directory, which we happen to have in %REPOS%.

%TRAC_ADMIN% "%TRAC_ENV%" changeset added "%REPOS%" "%REV%"

:: Based on either the symbolic name or the %REPOS% information,
:: Trac will figure out which repository (or which scoped repositories)
:: it has to synchronize.
