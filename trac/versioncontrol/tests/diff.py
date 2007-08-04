from trac.versioncontrol import diff

import unittest


class DiffTestCase(unittest.TestCase):

    def test_get_change_extent(self):
        self.assertEqual((3, 0), diff._get_change_extent('xxx', 'xxx'))
        self.assertEqual((0, 0), diff._get_change_extent('', 'xxx'))
        self.assertEqual((0, 0), diff._get_change_extent('xxx', ''))
        self.assertEqual((0, 0), diff._get_change_extent('xxx', 'yyy'))
        self.assertEqual((1, -1), diff._get_change_extent('xxx', 'xyx'))
        self.assertEqual((1, -1), diff._get_change_extent('xxx', 'xyyyx'))
        self.assertEqual((1, 0), diff._get_change_extent('xy', 'xzz'))
        self.assertEqual((1, -1), diff._get_change_extent('xyx', 'xzzx'))
        self.assertEqual((1, -1), diff._get_change_extent('xzzx', 'xyx'))

    def test_insert_blank_line(self):
        opcodes = diff._get_opcodes(['A', 'B'], ['A', 'B', ''],
                                     ignore_blank_lines=0)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())
        self.assertEqual(('insert', 2, 2, 2, 3), opcodes.next())

        opcodes = diff._get_opcodes(['A', 'B'], ['A', 'B', ''],
                                     ignore_blank_lines=1)
        self.assertEqual(('equal', 0, 2, 0, 3), opcodes.next())

        opcodes = diff._get_opcodes(['A'], ['A', 'B', ''],
                                     ignore_blank_lines=1)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('insert', 1, 1, 1, 3), opcodes.next())

    def test_delete_blank_line(self):
        opcodes = diff._get_opcodes(['A', 'B', ''], ['A', 'B'],
                                     ignore_blank_lines=0)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())
        self.assertEqual(('delete', 2, 3, 2, 2), opcodes.next())

        opcodes = diff._get_opcodes(['A', 'B', ''], ['A', 'B'],
                                     ignore_blank_lines=1)
        self.assertEqual(('equal', 0, 3, 0, 2), opcodes.next())

        opcodes = diff._get_opcodes(['A', 'B', ''], ['A'],
                                     ignore_blank_lines=1)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('delete', 1, 3, 1, 1), opcodes.next())

    def test_space_changes(self):
        opcodes = diff._get_opcodes(['A', 'B b'], ['A', 'B  b'],
                                     ignore_space_changes=0)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('replace', 1, 2, 1, 2), opcodes.next())

        opcodes = diff._get_opcodes(['A', 'B b'], ['A', 'B  b'],
                                     ignore_space_changes=1)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())

    def test_case_changes(self):
        opcodes = diff._get_opcodes(['A', 'B b'], ['A', 'B B'],
                                     ignore_case=0)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('replace', 1, 2, 1, 2), opcodes.next())

        opcodes = diff._get_opcodes(['A', 'B b'], ['A', 'B B'],
                                     ignore_case=1)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())

    def test_space_and_case_changes(self):
        opcodes = diff._get_opcodes(['A', 'B b'], ['A', 'B  B'],
                                     ignore_case=0, ignore_space_changes=0)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('replace', 1, 2, 1, 2), opcodes.next())

        opcodes = diff._get_opcodes(['A', 'B b'], ['A', 'B  B'],
                                     ignore_case=1, ignore_space_changes=1)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())

    def test_grouped_opcodes_context1(self):
        opcodes = diff._get_opcodes(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],
                                    ['A', 'B', 'C', 'd', 'e', 'f', 'G', 'H'])
        groups = diff._group_opcodes(opcodes, n=1)
        group = groups.next()
        self.assertEqual(('equal', 2, 3, 2, 3), group[0])
        self.assertEqual(('replace', 3, 6, 3, 6), group[1])
        self.assertEqual(('equal', 6, 7, 6, 7), group[2])

    def test_grouped_opcodes_insert_blank_line_at_top(self):
        """
        Regression test for #2090. Make sure that the equal block following an
        insert at the top of a file is correct.
        """
        opcodes = diff._get_opcodes(['B', 'C', 'D', 'E', 'F', 'G'],
                                    ['A', 'B', 'C', 'D', 'E', 'F', 'G'])
        groups = diff._group_opcodes(opcodes, n=3)
        self.assertEqual([('insert', 0, 0, 0, 1), ('equal', 0, 3, 1, 4)],
                         groups.next())

    def test_unified_diff_no_context(self):
        diff_lines = list(diff.unified_diff(['a'], ['b']))
        self.assertEqual(['@@ -1,1 +1,1 @@', '-a', '+b'], diff_lines)

    def test_quotes_not_marked_up(self):
        """Make sure that the escape calls leave quotes along, we don't need
        to escape them."""
        changes = diff.diff_blocks(['ab'], ['a"b'])
        self.assertEquals(len(changes), 1)
        blocks = changes[0]
        self.assertEquals(len(blocks), 1)
        block = blocks[0]
        self.assertEquals(block['type'], 'mod')
        self.assertEquals(str(block['base']['lines'][0]), 'a<del></del>b')
        self.assertEquals(str(block['changed']['lines'][0]), 'a<ins>"</ins>b')

    def test_whitespace_marked_up1(self):
        """Regression test for #5795"""
        changes = diff.diff_blocks(['*a'], [' *a'])
        block = changes[0][0]
        self.assertEquals(block['type'], 'mod')
        self.assertEquals(str(block['base']['lines'][0]), '<del></del>*a')
        self.assertEquals(str(block['changed']['lines'][0]), '<ins>&nbsp;</ins>*a')

    def test_whitespace_marked_up2(self):
        """Related to #5795"""
        changes = diff.diff_blocks(['   a'], ['   b'])
        block = changes[0][0]
        self.assertEquals(block['type'], 'mod')
        self.assertEquals(str(block['base']['lines'][0]), '&nbsp; &nbsp;<del>a</del>')
        self.assertEquals(str(block['changed']['lines'][0]), '&nbsp; &nbsp;<ins>b</ins>')

    def test_whitespace_marked_up3(self):
        """Related to #5795"""
        changes = diff.diff_blocks(['a   '], ['b   '])
        block = changes[0][0]
        self.assertEquals(block['type'], 'mod')
        self.assertEquals(str(block['base']['lines'][0]), '<del>a</del>&nbsp; &nbsp;')
        self.assertEquals(str(block['changed']['lines'][0]), '<ins>b</ins>&nbsp; &nbsp;')

    def test_expandtabs_works_right(self):
        """Regression test for #4557"""
        changes = diff.diff_blocks(['aa\tb'], ['aaxb'])
        block = changes[0][0]
        self.assertEquals(block['type'], 'mod')
        self.assertEquals(str(block['base']['lines'][0]), 'aa<del>&nbsp; &nbsp; &nbsp; </del>b')
        self.assertEquals(str(block['changed']['lines'][0]), 'aa<ins>x</ins>b')

def suite():
    return unittest.makeSuite(DiffTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
