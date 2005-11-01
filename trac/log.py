# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2005 Daniel Lundin <daniel@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Daniel Lundin <daniel@edgewall.com>

import logging
import logging.handlers
import sys

def logger_factory(logtype='syslog', logfile=None, level='WARNING',
                   logid='Trac'):
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
        hdlr = logging.handlers.MemoryHandler(1024)

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

    return logger
