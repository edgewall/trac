# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Daniel Lundin <daniel@edgewall.com>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Daniel Lundin <daniel@edgewall.com>

import sys
import util

def logger_factory(logtype='syslog', logfile=None, level='WARNING',
                   logid='Trac'):
    try:
        import logging, logging.handlers
        logger = logging.getLogger(logid)
        logtype = logtype.lower()
        if logtype == 'file':
            hdlr = logging.FileHandler(logfile)
        elif logtype in ['winlog', 'eventlog', 'nteventlog']:
            # Requires win32 extensions
            hdlr = logging.handlers.NTEventLogHandler(logid,
                                                      logtype='Application')
        elif logtype in ['syslog', 'unix']:
            hdlr = logging.handlers.SysLogHandler('/dev/log')
        elif logtype in ['stderr']:
            hdlr = logging.StreamHandler(sys.stderr)
        else:
            raise ValueError

        format = 'Trac[%(module)s] %(levelname)s: %(message)s'
        if logtype == 'file':
            format = '%(asctime)s ' + format 
        datefmt = ''
        level = level.upper()
        if level in ['DEBUG', 'ALL']:
            logger.setLevel(logging.DEBUG)
            datefmt = '%X'
        elif level == 'INFO':
            logger.setLevel(logging.INFO)
        elif level == 'ERROR':
            logger.setLevel(logging.ERROR)
        elif level == 'CRITICAL':
            logger.setLevel(logging.CRITICAL)
        else:
            logger.setLevel(logging.WARNING)
        formatter = logging.Formatter(format,datefmt)
        hdlr.setFormatter(formatter)
        logger.addHandler(hdlr) 

    # Logging only supported in Python >= 2.3
    # Disable logging by using a generic 'black hole' class
    except (ImportError, ValueError):
        class DummyLogger:
            """The world's most fake logger."""
            def __noop(self, *args):
                pass
            debug = info = warning = error = critical = log = exception = __noop
            warn = fatal = __noop
            getEffectiveLevel = lambda self: 0
            isEnabledFor = lambda self, level: 0
        logger = DummyLogger()
    return logger
