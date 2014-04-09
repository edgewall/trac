# -*- coding: utf-8 -*-
#
# Copyright (C) 2010-2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import unittest

from trac.db.util import sql_escape_percent

# TODO: test IterableCursor, ConnectionWrapper

class SQLEscapeTestCase(unittest.TestCase):
    def test_sql_escape_percent(self):
        self.assertEqual("%", sql_escape_percent("%"))
        self.assertEqual("'%%'", sql_escape_percent("'%'"))
        self.assertEqual("''%''", sql_escape_percent("''%''"))
        self.assertEqual("'''%%'''", sql_escape_percent("'''%'''"))
        self.assertEqual("'''%%'", sql_escape_percent("'''%'"))
        self.assertEqual("%s", sql_escape_percent("%s"))
        self.assertEqual("% %", sql_escape_percent("% %"))
        self.assertEqual("%s %i", sql_escape_percent("%s %i"))
        self.assertEqual("'%%s'", sql_escape_percent("'%s'"))
        self.assertEqual("'%% %%'", sql_escape_percent("'% %'"))
        self.assertEqual("'%%s %%i'", sql_escape_percent("'%s %i'"))

        self.assertEqual("%", sql_escape_percent("%"))
        self.assertEqual("`%%`", sql_escape_percent("`%`"))
        self.assertEqual("``%``", sql_escape_percent("``%``"))
        self.assertEqual("```%%```", sql_escape_percent("```%```"))
        self.assertEqual("```%%`", sql_escape_percent("```%`"))
        self.assertEqual("%s", sql_escape_percent("%s"))
        self.assertEqual("% %", sql_escape_percent("% %"))
        self.assertEqual("%s %i", sql_escape_percent("%s %i"))
        self.assertEqual("`%%s`", sql_escape_percent("`%s`"))
        self.assertEqual("`%% %%`", sql_escape_percent("`% %`"))
        self.assertEqual("`%%s %%i`", sql_escape_percent("`%s %i`"))

        self.assertEqual('%', sql_escape_percent('%'))
        self.assertEqual('"%%"', sql_escape_percent('"%"'))
        self.assertEqual('""%""', sql_escape_percent('""%""'))
        self.assertEqual('"""%%"""', sql_escape_percent('"""%"""'))
        self.assertEqual('"""%%"', sql_escape_percent('"""%"'))
        self.assertEqual('%s', sql_escape_percent('%s'))
        self.assertEqual('% %', sql_escape_percent('% %'))
        self.assertEqual('%s %i', sql_escape_percent('%s %i'))
        self.assertEqual('"%%s"', sql_escape_percent('"%s"'))
        self.assertEqual('"%% %%"', sql_escape_percent('"% %"'))
        self.assertEqual('"%%s %%i"', sql_escape_percent('"%s %i"'))

        self.assertEqual("""'%%?''"%%s`%%i`%%%%"%%S'""",
                         sql_escape_percent("""'%?''"%s`%i`%%"%S'"""))
        self.assertEqual("""`%%?``'%%s"%%i"%%%%'%%S`""",
                         sql_escape_percent("""`%?``'%s"%i"%%'%S`"""))
        self.assertEqual('''"%%?""`%%s'%%i'%%%%`%%S"''',
                         sql_escape_percent('''"%?""`%s'%i'%%`%S"'''))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(SQLEscapeTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
