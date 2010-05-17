# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2006 Christian Boos <cboos@neuf.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Daniel Lundin <daniel@edgewall.com>

import logging
import logging.handlers
import sys

def logger_handler_factory(logtype='syslog', logfile=None, level='WARNING',
                           logid='Trac', format=None):
    logger = logging.getLogger(logid)
    logtype = logtype.lower()
    if logtype == 'file':
        hdlr = logging.FileHandler(logfile)
    elif logtype in ('winlog', 'eventlog', 'nteventlog'):
        # Requires win32 extensions
        hdlr = logging.handlers.NTEventLogHandler(logid,
                                                  logtype='Application')
    elif logtype in ('syslog', 'unix'):
        hdlr = logging.handlers.SysLogHandler('/dev/log')
    elif logtype in ('stderr'):
        hdlr = logging.StreamHandler(sys.stderr)
    else:
        hdlr = logging.handlers.BufferingHandler(0)
        # Note: this _really_ throws away log events, as a `MemoryHandler`
        # would keep _all_ records in case there's no target handler (a bug?)

    if not format:
        format = 'Trac[%(module)s] %(levelname)s: %(message)s'
        if logtype in ('file', 'stderr'):
            format = '%(asctime)s ' + format
    datefmt = ''
    if logtype == 'stderr':
        datefmt = '%X'
    level = level.upper()
    if level in ('DEBUG', 'ALL'):
        logger.setLevel(logging.DEBUG)
    elif level == 'INFO':
        logger.setLevel(logging.INFO)
    elif level == 'ERROR':
        logger.setLevel(logging.ERROR)
    elif level == 'CRITICAL':
        logger.setLevel(logging.CRITICAL)
    else:
        logger.setLevel(logging.WARNING)
    formatter = logging.Formatter(format, datefmt)
    hdlr.setFormatter(formatter)
    logger.addHandler(hdlr)

    # Remember our handler so that we can remove it later
    logger._trac_handler = hdlr 

    return logger, hdlr

def logger_factory(logtype='syslog', logfile=None, level='WARNING',
                   logid='Trac', format=None):
    return logger_handler_factory(logtype, logfile, level, logid, format)[0]
