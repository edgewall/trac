# -*- coding: utf-8 -*-
#
# Copyright (C) 2010-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

try:
    import threading
except ImportError:
    import dummy_threading as threading
    threading._get_ident = lambda: 0


class ThreadLocal(threading.local):
    """A thread-local storage allowing to set default values on construction.
    """
    def __init__(self, **kwargs):
        threading.local.__init__(self)
        self.__dict__.update(kwargs)


try:
    threading.get_ident  # since Python 3.3
except AttributeError:
    get_thread_id = threading._get_ident
else:
    get_thread_id = threading.get_ident
