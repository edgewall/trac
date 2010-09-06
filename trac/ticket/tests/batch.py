from trac.test import Mock, EnvironmentStub
from trac.ticket.batch import BatchModifyModule
from trac.ticket.model import Ticket
from trac.util.datefmt import utc

import unittest

class BatchModifyTestCase(unittest.TestCase):
    
    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.req = Mock(href=self.env.href, authname='anonymous', tz=utc)
    
    def assertCommentAdded(self, ticket_id, comment):
        ticket = Ticket(self.env, int(ticket_id))
        changes = ticket.get_changelog()
        comment_change = [c for c in changes if c[2] == 'comment'][0]
        self.assertEqual(comment_change[2], comment)
    
    def assertFieldChanged(self, ticket_id, field, new_value):
        ticket = Ticket(self.env, int(ticket_id))
        changes = ticket.get_changelog()
        field_change = [c for c in changes if c[2] == field][0]
        self.assertEqual(field_change[4], new_value)
    
    def _merge_keywords_test_helper(self, original, new):
        batch = BatchModifyModule(self.env)
        return batch._merge_keywords(original, new)
    
    def _insert_ticket(self, summary, **kw):
        """Helper for inserting a ticket into the database"""
        ticket = Ticket(self.env)
        for k, v in kw.items():
            ticket[k] = v
        return ticket.insert()
    
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
        
    def test_get_selected_tickets_returns_list_of_tickets(self):
        self.req.args = { 'selected_tickets' : '1,2,3' }        
        batch = BatchModifyModule(self.env)
        selected_tickets = batch._get_selected_tickets(self.req)
        self.assertEqual(selected_tickets, ['1', '2', '3'])
        
    def test_get_selected_tickets_returns_empty_list_when_nothing_selected(self):
        self.req.args = { 'selected_tickets' : '' }        
        batch = BatchModifyModule(self.env)
        selected_tickets = batch._get_selected_tickets(self.req)
        self.assertEqual(selected_tickets, [])
        
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
        
    def test_save_ticket_changes_saves_comment_to_all_selected_tickets(self):
        first_ticket_id = self._insert_ticket('Test 1', reporter='joe')
        second_ticket_id = self._insert_ticket('Test 2', reporter='joe')
        selected_tickets = [first_ticket_id, second_ticket_id]
        
        batch = BatchModifyModule(self.env)
        batch._save_ticket_changes(self.req, selected_tickets, {}, "comment")
        
        self.assertCommentAdded(first_ticket_id, "comment")
        self.assertCommentAdded(second_ticket_id, "comment")
    
    def test_save_ticket_changes_saves_values_to_all_selected_tickets(self):
        first_ticket_id = self._insert_ticket('Test 1', reporter='joe', 
                                              component="foo")
        second_ticket_id = self._insert_ticket('Test 2', reporter='joe')
        selected_tickets = [first_ticket_id, second_ticket_id]
        new_values = { "component" : "bar" } 
        
        batch = BatchModifyModule(self.env)
        batch._save_ticket_changes(self.req, selected_tickets, new_values, "")
        
        self.assertFieldChanged(first_ticket_id, "component", "bar")
        self.assertFieldChanged(second_ticket_id, "component", "bar")
    
    def test_save_ticket_changes_can_treat_multiple_fields_as_lists(self):
        self.env.config.set('batchmod', 'fields_as_lists', 
                            'keywords,stakeholders')
        self.env.config.set('ticket-custom', 'stakeholders', 'text')
        first_ticket_id = self._insert_ticket('Test 1', reporter='joe', 
                                              keywords="foo,bar",
                                              stakeholders="shirley")
        second_ticket_id = self._insert_ticket('Test 2', reporter='joe',
                                               keywords="foo", 
                                               stakeholders="jim")
        selected_tickets = [first_ticket_id, second_ticket_id]
        values = { "keywords" : "bar,baz", "stakeholders" : "joe" }
        
        batch = BatchModifyModule(self.env)
        batch._save_ticket_changes(self.req, selected_tickets, values, "")
        
        self.assertFieldChanged(first_ticket_id, "stakeholders", "shirley,joe")
        self.assertFieldChanged(second_ticket_id, "keywords", "foo,bar")
        self.assertFieldChanged(second_ticket_id, "stakeholders", "jim,joe")
    
def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(BatchModifyTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')