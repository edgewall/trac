from trac import Diff

import unittest


class DiffTestCase(unittest.TestCase):

    def test_get_change_extent(self):
        self.assertEqual((3, 0), Diff._get_change_extent('xxx', 'xxx'))
        self.assertEqual((0, 0), Diff._get_change_extent('', 'xxx'))
        self.assertEqual((0, 0), Diff._get_change_extent('xxx', ''))
        self.assertEqual((0, 0), Diff._get_change_extent('xxx', 'yyy'))
        self.assertEqual((1, -1), Diff._get_change_extent('xxx', 'xyx'))
        self.assertEqual((1, -1), Diff._get_change_extent('xxx', 'xyyyx'))
        self.assertEqual((1, 0), Diff._get_change_extent('xy', 'xzz'))
        self.assertEqual((1, -1), Diff._get_change_extent('xyx', 'xzzx'))
        self.assertEqual((1, -1), Diff._get_change_extent('xzzx', 'xyx'))

    def test_insert_blank_line(self):
        opcodes = Diff._get_opcodes(['A', 'B'], ['A', 'B', ''],
                                     ignore_blank_lines=0)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())
        self.assertEqual(('insert', 2, 2, 2, 3), opcodes.next())

        opcodes = Diff._get_opcodes(['A', 'B'], ['A', 'B', ''],
                                     ignore_blank_lines=1)
        self.assertEqual(('equal', 0, 2, 0, 3), opcodes.next())

        opcodes = Diff._get_opcodes(['A'], ['A', 'B', ''],
                                     ignore_blank_lines=1)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('insert', 1, 1, 1, 3), opcodes.next())

    def test_delete_blank_line(self):
        opcodes = Diff._get_opcodes(['A', 'B', ''], ['A', 'B'],
                                     ignore_blank_lines=0)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())
        self.assertEqual(('delete', 2, 3, 2, 2), opcodes.next())

        opcodes = Diff._get_opcodes(['A', 'B', ''], ['A', 'B'],
                                     ignore_blank_lines=1)
        self.assertEqual(('equal', 0, 3, 0, 2), opcodes.next())

        opcodes = Diff._get_opcodes(['A', 'B', ''], ['A'],
                                     ignore_blank_lines=1)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('delete', 1, 3, 1, 1), opcodes.next())

    def test_space_changes(self):
        opcodes = Diff._get_opcodes(['A', 'B b'], ['A', 'B  b'],
                                     ignore_space_changes=0)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('replace', 1, 2, 1, 2), opcodes.next())

        opcodes = Diff._get_opcodes(['A', 'B b'], ['A', 'B  b'],
                                     ignore_space_changes=1)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())

    def test_case_changes(self):
        opcodes = Diff._get_opcodes(['A', 'B b'], ['A', 'B B'],
                                     ignore_case=0)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('replace', 1, 2, 1, 2), opcodes.next())

        opcodes = Diff._get_opcodes(['A', 'B b'], ['A', 'B B'],
                                     ignore_case=1)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())

    def test_space_and_case_changes(self):
        opcodes = Diff._get_opcodes(['A', 'B b'], ['A', 'B  B'],
                                     ignore_case=0, ignore_space_changes=0)
        self.assertEqual(('equal', 0, 1, 0, 1), opcodes.next())
        self.assertEqual(('replace', 1, 2, 1, 2), opcodes.next())

        opcodes = Diff._get_opcodes(['A', 'B b'], ['A', 'B  B'],
                                     ignore_case=1, ignore_space_changes=1)
        self.assertEqual(('equal', 0, 2, 0, 2), opcodes.next())

    def test_grouped_opcodes_context1(self):
        opcodes = Diff._get_opcodes(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],
                                     ['A', 'B', 'C', 'd', 'e', 'f', 'G', 'H'])
        groups = Diff._group_opcodes(opcodes, n=1)
        group = groups.next()
        self.assertEqual(('equal', 2, 3, 2, 3), group[0])
        self.assertEqual(('replace', 3, 6, 3, 6), group[1])
        self.assertEqual(('equal', 6, 8, 6, 8), group[2])


def suite():
    return unittest.makeSuite(DiffTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
