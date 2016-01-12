# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
# Copyright (C) 2015 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

# ------------------------------------------------------------------
#  This is a PowerShell script implementing the build steps used by
#  the AppVeyor Continuous Delivery service for Windows, Trac project
#  (https://ci.appveyor.com/project/cboos/trac)
# ------------------------------------------------------------------
 
# ------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------

# Update the following in case the build environment on AppVeyor changes.
# See in particular:
#  - http://www.appveyor.com/docs/installed-software#python
#  - http://www.appveyor.com/docs/installed-software#mingw-msys-cygwin
#  - http://www.appveyor.com/docs/services-databases#mysql
#  - http://www.appveyor.com/docs/services-databases#postgresql

$msysHome = 'C:\msys64\usr\bin'
$deps     = 'C:\projects\dependencies'

# External dependencies

$pipCommonPackages = @(
    'genshi', 
    'babel', 
    'twill==0.9.1',
    'configobj',
    'docutils', 
    'pygments',
    'pytz'
)


$fcrypt    = "$deps\fcrypt-1.3.1.tar.gz"
$fcryptUrl = 'http://www.carey.geek.nz/code/python-fcrypt/fcrypt-1.3.1.tar.gz'

$pipPackages = @{ 
    '1.0-stable' = @($fcrypt); 
    trunk = @('passlib');
}


# ------------------------------------------------------------------
# "Environment" environment variables
# ------------------------------------------------------------------

# In the build matrix, we can set arbitrary environment variables
# which together define a particular software configuration that
# will be tested.

# These variables are:
#  - PYTHONHOME: the version of python we are testing
#  - TRAC_TEST_DB_URI: the database backend we are testing
#  - SKIP_ENV: don't perform any step with this environment (optional)
#  - SKIP_BUILD: don't execute the Build step for this environment (optional)
#  - SKIP_TEST: don't execute the Test step for this environment (optional)
#
# Note that any combination should work, except for MySQL where we expect to
# use a Conda version of Python.
 
# "Aliases"

$pyHome = $env:PYTHONHOME
$usingMysql = $env:TRAC_TEST_DB_URI -match 'mysql'
$usingPostgresql = $env:TRAC_TEST_DB_URI -match 'postgres'
$skipInstall = [bool]$env:SKIP_ENV
$skipBuild = $env:SKIP_BUILD -or $env:SKIP_ENV
$skipTest = $env:SKIP_TEST -or $env:SKIP_ENV

$pyVersion = if ([string](& python.exe -V 2>&1) -match ' (\d\.\d)') { 
    $Matches[1] 
}

$branch = $env:APPVEYOR_REPO_BRANCH


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------

# Documentation for AppVeyor API (Add-AppveyorMessage, etc.) can be found at:
# http://www.appveyor.com/docs/build-worker-api

function Step([string]$name, [bool]$skip) {
    if ($skip) {
        $message = "Skipping step $name"
        Write-Host $message
        Add-AppveyorMessage -Message $message
    } else {
        Write-Host @"

------------------------------------------------------------------
$name
------------------------------------------------------------------
"@
    }
}


# ------------------------------------------------------------------
# Steps
# ------------------------------------------------------------------

# Setting up the PATH (common to all steps)

$env:Path = "$pyHome;$pyHome\Scripts;$msysHome;$($env:Path)"

function Trac-Install {

    Step INSTALL $skipInstall

    if ($skipInstall) {
	return
    }

    if (-not (Test-Path $deps)) {
	& mkdir $deps
    }

    # Download fcrypt if needed (only for 1.0-stable after #12239)

    if ($branch -eq '1.0-stable') {
	if (-not (Test-Path $fcrypt)) {
	    & curl.exe -sS $fcryptUrl -o $fcrypt
	}
    } 

    # Install packages via pip

    # pip in Python 2.6 triggers the following warning:
    # https://urllib3.readthedocs.org/en/latest/security.html#insecureplatformwarning
    if ($pyVersion -eq '2.6') {
         $ignoreWarnings = @(
	     '-W', 'ignore:A true SSLContext object is not available'
	 )
    }

    function pip() {
	python.exe $ignoreWarnings -m pip.__main__ @args
        # Note: -m pip works only in 2.7, -m pip.__main__ works in both
    }

    & pip --version
    & pip install $pipCommonPackages $pipPackages.$branch

    if ($usingMysql) {
	#
	# $TRAC_TEST_DB_URI=
	# "postgres://tracuser:password@localhost/trac?schema=tractest"
	#

	# It's easier to get MySQL-python support on Windows using Conda
	& conda.exe install -qy mysql-python

	Add-AppveyorMessage -Message "1.1. mysql-python package installed" `
	  -Category Information

    }
    elseif ($usingPostgres) {
	#
	# $TRAC_TEST_DB_URI=
	# "postgres://tracuser:password@localhost/trac?schema=tractest"
	#

	& pip install psycopg2

	Add-AppveyorMessage -Message "1.1. psycopg2 package installed" `
	  -Category Information
    }

    & pip list

    # Prepare local Makefile.cfg

    ".uri = $env:TRAC_TEST_DB_URI" | out-file -encoding ASCII 'Makefile.cfg'

    # Note 1: echo would create an UCS-2 file with a BOM, make.exe
    #         doesn't appreciate...

    # Note 2: we can't do more at this stage, as the services
    #         (MySQL/PostgreSQL) are not started yet.
}
