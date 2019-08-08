# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2019 Edgewall Software
# Copyright (C) 2003-2005 Daniel Lundin <daniel@edgewall.com>
# Copyright (C) 2006 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Daniel Lundin <daniel@edgewall.com>

import logging
import logging.handlers
import sys

LOG_TYPES = ('file', 'stderr', 'syslog', 'eventlog', 'none')
LOG_TYPE_ALIASES = ('winlog', 'nteventlog', 'unix')
LOG_LEVELS = ('INFO', 'CRITICAL', 'ERROR', 'WARNING', 'DEBUG')
LOG_LEVEL_ALIASES_MAP = {'WARN': 'WARNING', 'ALL': 'DEBUG'}
LOG_LEVEL_ALIASES = tuple(sorted(LOG_LEVEL_ALIASES_MAP))


LOG_LEVEL_MAP = {
    'DEBUG': logging.DEBUG, 'ALL': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING, 'WARN': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}


def logger_handler_factory(logtype='syslog', logfile=None, level='WARNING',
                           logid='Trac', format=None):
    logger = logging.getLogger(logid)
    logtype = logtype.lower()
    if logtype == 'file':
        hdlr = logging.FileHandler(logfile)
    elif logtype in ('eventlog', 'winlog', 'nteventlog'):
        # Requires win32 extensions
        hdlr = logging.handlers.NTEventLogHandler(logid,
                                                  logtype='Application')
    elif logtype in ('syslog', 'unix'):
        hdlr = logging.handlers.SysLogHandler('/dev/log')
    elif logtype == 'stderr':
        hdlr = logging.StreamHandler(sys.stderr)
    else:
        hdlr = logging.NullHandler()

    level = level.upper()
    level_as_int = LOG_LEVEL_MAP.get(level)
    if level_as_int is None:
        # Should never be reached because level is restricted through
        # ChoiceOption, therefore message is intentionally left untranslated
        raise AssertionError("Unrecognized log level '%s'" % level)
    logger.setLevel(level_as_int)

    if not format:
        format = 'Trac[%(module)s] %(levelname)s: %(message)s'
        if logtype in ('file', 'stderr'):
            format = '%(asctime)s ' + format
    datefmt = '%X' if logtype == 'stderr' else ''
    formatter = logging.Formatter(format, datefmt)
    hdlr.setFormatter(formatter)

    return logger, hdlr


def shutdown(logger):
    for handler in logger.handlers[:]:
        handler.flush()
        handler.close()
        logger.removeHandler(handler)
