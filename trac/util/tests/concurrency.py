# -*- coding: utf-8 -*-
#
# Copyright (C) 2010 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import threading
import unittest

from trac.util.concurrency import ThreadLocal


class ThreadLocalTestCase(unittest.TestCase):

    def test_thread_local(self):
        local = ThreadLocal(a=1, b=2)
        local.b = 3
        local.c = 4
        local_dict = [local.__dict__.copy()]
        def f():
            local.b = 5
            local.d = 6
            local_dict.append(local.__dict__.copy())
        thread = threading.Thread(target=f)
        thread.start()
        thread.join()
        self.assertEqual(dict(a=1, b=3, c=4), local_dict[0])
        self.assertEqual(dict(a=1, b=5, d=6), local_dict[1])


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ThreadLocalTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
