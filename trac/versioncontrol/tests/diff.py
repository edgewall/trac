# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.versioncontrol import diff

import unittest

def get_opcodes(*args, **kwargs):
    for hunk in diff.get_filtered_hunks(*args, **kwargs):
        for opcode in hunk:
            yield opcode

class DiffTestCase(unittest.TestCase):

    def testget_change_extent(self):
        self.assertEqual((3, 0), diff.get_change_extent('xxx', 'xxx'))
        self.assertEqual((0, 0), diff.get_change_extent('', 'xxx'))
        self.assertEqual((0, 0), diff.get_change_extent('xxx', ''))
        self.assertEqual((0, 0), diff.get_change_extent('xxx', 'yyy'))
        self.assertEqual((1, -1), diff.get_change_extent('xxx', 'xyx'))
        self.assertEqual((1, -1), diff.get_change_extent('xxx', 'xyyyx'))
        self.assertEqual((1, 0), diff.get_change_extent('xy', 'xzz'))
        self.assertEqual((1, -1), diff.get_change_extent('xyx', 'xzzx'))
        self.assertEqual((1, -1), diff.get_change_extent('xzzx', 'xyx'))

    def test_insert_blank_line(self):
        opcodes = get_opcodes(['A', 'B'], ['A', 'B', ''], ignore_blank_lines=0)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())
        self.assertEqual(('insert', 2, 2, 2, 3), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

        opcodes = get_opcodes(['A', 'B'], ['A', 'B', ''], ignore_blank_lines=1)
        self.assertEqual(('equal', 0, 2, 0, 3), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

        opcodes = get_opcodes(['A'], ['A', 'B', ''], ignore_blank_lines=0)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('insert', 1, 1, 1, 3), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

        opcodes = get_opcodes(['A'], ['A', 'B', ''], ignore_blank_lines=1)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('insert', 1, 1, 1, 3), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

    def test_delete_blank_line(self):
        opcodes = get_opcodes(['A', 'B', ''], ['A', 'B'], ignore_blank_lines=0)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())
        self.assertEqual(('delete', 2, 3, 2, 2), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

        opcodes = get_opcodes(['A', 'B', ''], ['A', 'B'], ignore_blank_lines=1)
        self.assertEqual(('equal', 0, 3, 0, 2), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

        opcodes = get_opcodes(['A', 'B', ''], ['A'], ignore_blank_lines=0)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('delete', 1, 3, 1, 1), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

        opcodes = get_opcodes(['A', 'B', ''], ['A'], ignore_blank_lines=1)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('delete', 1, 3, 1, 1), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

    def test_space_changes(self):
        opcodes = get_opcodes(['A', 'B b'], ['A', 'B  b'],
                              ignore_space_changes=0)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('replace', 1, 2, 1, 2), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

        opcodes = get_opcodes(['A', 'B b'], ['A', 'B  b'],
                              ignore_space_changes=1)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

    def test_space_changes_2(self):
        left = """\
try:
    try:
        func()
        commit()
    except:
        rollback()
finally:
    cleanup()
"""
        left = left.splitlines()
        right = """\
try:
    func()
    commit()
except:
    rollback()
finally:
    cleanup()
"""
        right = right.splitlines()
        opcodes = get_opcodes(left, right, ignore_space_changes=0)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('replace', 1, 6, 1, 5), opcodes.next())
        self.assertEqual(('equal', 6, 8, 5, 7), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

        opcodes = get_opcodes(left, right, ignore_space_changes=1)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('delete', 1, 2, 1, 1), opcodes.next())
        self.assertEqual(('equal', 2, 4, 1, 3), opcodes.next())
        self.assertEqual(('replace', 4, 5, 3, 4), opcodes.next())
        self.assertEqual(('equal', 5, 8, 4, 7), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

    def test_case_changes(self):
        opcodes = get_opcodes(['A', 'B b'], ['A', 'B B'], ignore_case=0)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('replace', 1, 2, 1, 2), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

        opcodes = get_opcodes(['A', 'B b'], ['A', 'B B'], ignore_case=1)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

    def test_space_and_case_changes(self):
        opcodes = get_opcodes(['A', 'B b'], ['A', 'B  B'],
                              ignore_case=0, ignore_space_changes=0)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('replace', 1, 2, 1, 2), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

        opcodes = get_opcodes(['A', 'B b'], ['A', 'B  B'],
                              ignore_case=1, ignore_space_changes=1)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())
        self.assertRaises(StopIteration, opcodes.next)

    def test_grouped_opcodes_context1(self):
        groups = diff.get_filtered_hunks(
            ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],
            ['A', 'B', 'C', 'd', 'e', 'f', 'G', 'H'], context=1)
        group = groups.next()
        self.assertRaises(StopIteration, groups.next)
        self.assertEqual(('equal', 2, 3, 2, 3), group[0])
        self.assertEqual(('replace', 3, 6, 3, 6), group[1])
        self.assertEqual(('equal', 6, 7, 6, 7), group[2])

    def test_grouped_opcodes_context1_ignorecase(self):
        old = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        new = ['X', 'B', 'C', 'd', 'e', 'f', 'G', 'Y']
        groups = diff.get_filtered_hunks(old, new, context=1, ignore_case=1)
        group = groups.next()
        self.assertEqual([('replace', 0, 1, 0, 1), ('equal', 1, 2, 1, 2)],
                         group)
        group = groups.next()
        self.assertRaises(StopIteration, groups.next)
        self.assertEqual([('equal', 6, 7, 6, 7), ('replace', 7, 8, 7, 8)],
                         group)

    def test_grouped_opcodes_full_context(self):
        old = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        new = ['X', 'B', 'C', 'd', 'e', 'f', 'G', 'Y']
        groups = diff.get_filtered_hunks(old, new, context=None)
        group = groups.next()
        self.assertRaises(StopIteration, groups.next)
        self.assertEqual([
                ('replace', 0, 1, 0, 1),
                ('equal', 1, 3, 1, 3),
                ('replace', 3, 6, 3, 6),
                ('equal', 6, 7, 6, 7),
                ('replace', 7, 8, 7, 8),
                ], group)

        groups = diff.get_filtered_hunks(old, new, context=None, ignore_case=1)
        group = groups.next()
        self.assertRaises(StopIteration, groups.next)
        self.assertEqual([
                ('replace', 0, 1, 0, 1),
                ('equal', 1, 7, 1, 7),
                ('replace', 7, 8, 7, 8),
                ], group)

    def test_grouped_opcodes_insert_blank_line_at_top(self):
        """
        Regression test for #2090. Make sure that the equal block following an
        insert at the top of a file is correct.
        """
        groups = diff.get_filtered_hunks(['B', 'C', 'D', 'E', 'F', 'G'],
                                         ['A', 'B', 'C', 'D', 'E', 'F', 'G'],
                                         context=3)
        self.assertEqual([('insert', 0, 0, 0, 1), ('equal', 0, 3, 1, 4)],
                         groups.next())
        self.assertRaises(StopIteration, groups.next)

    def test_unified_diff_no_context(self):
        diff_lines = list(diff.unified_diff(['a'], ['b']))
        self.assertEqual(['@@ -1,1 +1,1 @@', '-a', '+b'], diff_lines)

    def test_quotes_not_marked_up(self):
        """Make sure that the escape calls leave quotes along, we don't need
        to escape them."""
        changes = diff.diff_blocks(['ab'], ['a"b'])
        self.assertEqual(len(changes), 1)
        blocks = changes[0]
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertEqual(block['type'], 'mod')
        self.assertEqual(str(block['base']['lines'][0]), 'a<del></del>b')
        self.assertEqual(str(block['changed']['lines'][0]), 'a<ins>"</ins>b')

    def test_whitespace_marked_up1(self):
        """Regression test for #5795"""
        changes = diff.diff_blocks(['*a'], [' *a'])
        block = changes[0][0]
        self.assertEqual(block['type'], 'mod')
        self.assertEqual(str(block['base']['lines'][0]), '<del></del>*a')
        self.assertEqual(str(block['changed']['lines'][0]),
                         '<ins>&nbsp;</ins>*a')

    def test_whitespace_marked_up2(self):
        """Related to #5795"""
        changes = diff.diff_blocks(['   a'], ['   b'])
        block = changes[0][0]
        self.assertEqual(block['type'], 'mod')
        self.assertEqual(str(block['base']['lines'][0]),
                         '&nbsp; &nbsp;<del>a</del>')
        self.assertEqual(str(block['changed']['lines'][0]),
                         '&nbsp; &nbsp;<ins>b</ins>')

    def test_whitespace_marked_up3(self):
        """Related to #5795"""
        changes = diff.diff_blocks(['a   '], ['b   '])
        block = changes[0][0]
        self.assertEqual(block['type'], 'mod')
        self.assertEqual(str(block['base']['lines'][0]),
                         '<del>a</del>&nbsp; &nbsp;')
        self.assertEqual(str(block['changed']['lines'][0]),
                         '<ins>b</ins>&nbsp; &nbsp;')

    def test_expandtabs_works_right(self):
        """Regression test for #4557"""
        changes = diff.diff_blocks(['aa\tb'], ['aaxb'])
        block = changes[0][0]
        self.assertEqual(block['type'], 'mod')
        self.assertEqual(str(block['base']['lines'][0]),
                         'aa<del>&nbsp; &nbsp; &nbsp; </del>b')
        self.assertEqual(str(block['changed']['lines'][0]),
                         'aa<ins>x</ins>b')

def test_suite():
    return unittest.makeSuite(DiffTestCase)

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
