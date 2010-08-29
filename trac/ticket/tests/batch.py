from trac.test import Mock, EnvironmentStub, MockPerm
from trac.ticket.batch import BatchModifyModule
from trac.util.datefmt import utc

import unittest

class BatchModifyTestCase(unittest.TestCase):
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.req = Mock(href=self.env.href, authname='anonymous', tz=utc)
        
    def _merge_keywords_test_helper(self, original, new):
        batch = BatchModifyModule(self.env)
        return batch._merge_keywords(original, new)
    
    def test_get_new_ticket_values_ignores_summary_reporter_and_description(self):
        """These cannot be added through the UI, but if somebody tries
        to build their own POST data they will be ignored."""
        batch = BatchModifyModule(self.env)
        self.req.args = {}
        self.req.args['batchmod_value_summary'] = 'test ticket'
        self.req.args['batchmod_value_reporter'] = 'anonymous'
        self.req.args['batchmod_value_description'] = 'synergize the widgets'
        values = batch._get_new_ticket_values(self.req)
        self.assertEqual(len(values), 0)
        
    def test_get_new_ticket_values_adds_batchmod_value_data_from_request(self):
        """These cannot be added through the UI, but if somebody tries
        to build their own POST data they will be ignored."""
        batch = BatchModifyModule(self.env)
        self.req.args = {}
        self.req.args['batchmod_value_milestone'] = 'milestone1'
        values = batch._get_new_ticket_values(self.req)
        self.assertEqual(values['milestone'], 'milestone1')
    
    def test_check_for_resolution_sets_status_to_closed_if_resolution(self):
        batch = BatchModifyModule(self.env)
        values = { 'resolution' : 'fixed' }
        batch._check_for_resolution(values)
        self.assertEqual(values['status'], 'closed')
        
    def test_check_for_resolution_adds_nothing_if_no_resolution(self):
        batch = BatchModifyModule(self.env)
        values = {}
        batch._check_for_resolution(values)
        self.assertEqual(len(values), 0)
        
    def test_remove_resolution_if_not_closed_keeps_resolution_if_status_is_closed(self):
        batch = BatchModifyModule(self.env)
        values = { 'status' : 'closed'}
        batch._remove_resolution_if_not_closed(values)
        self.assertFalse(values.has_key('resolution'))
        
    def test_remove_resolution_if_not_closed_sets_resolution_to_nothing_if_status_is_closed(self):
        batch = BatchModifyModule(self.env)
        values = { 'status' : 'reopened'}
        batch._remove_resolution_if_not_closed(values)
        self.assertEqual(values['resolution'], '')
        
    def test_merge_keywords_adds_new_keywords_to_empty_list(self):
        combined = self._merge_keywords_test_helper('', 'foo, bar')
        self.assertEqual(combined, 'foo,bar')
    
    def test_merge_keywords_appends_new_keyword_to_non_empty_list(self):
        combined = self._merge_keywords_test_helper('foo,bar', 'baz')
        self.assertEqual(combined, 'foo,bar,baz')
    
    def test_merge_keywords_does_not_duplicate_existing_keywords(self):
        combined = self._merge_keywords_test_helper('foo,bar', 'bar,baz')
        self.assertEqual(combined, 'foo,bar,baz')
        
    def test_merge_keywords_removes_keywords_beginning_with_dash(self):
        combined = self._merge_keywords_test_helper('foo,bar', '-bar')
        self.assertEqual(combined, 'foo')
    
    def test_merge_keywords_ignores_removing_keywords_that_are_not_in_original_list(self):
        combined = self._merge_keywords_test_helper('foo,bar', '-baz')
        self.assertEqual(combined, 'foo,bar')
    
    def test_merge_keywords_can_use_custom_separator_and_connector_strings(self):
        self.env.config.set('batchmod', 'list_separator_regex', '|')
        self.env.config.set('batchmod', 'list_connector_string', '|')
        combined = self._merge_keywords_test_helper('foo|bar', 'baz')
        self.assertEqual(combined, 'foo|bar|baz') 
    
def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(BatchModifyTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')