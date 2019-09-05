# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import os
import unittest

from trac.mimeview.api import Mimeview
from trac.test import EnvironmentStub, MockPerm, MockRequest
from trac.ticket.test import insert_ticket
from trac.ticket.web_ui import TicketModule


class TicketConversionTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.config.set('trac', 'templates_dir',
                            os.path.join(os.path.dirname(self.env.path),
                                         'templates'))
        self.ticket_module = TicketModule(self.env)
        self.mimeview = Mimeview(self.env)
        self.req = MockRequest(self.env, authname='anonymous')

    def tearDown(self):
        self.env.reset_db()

    def _create_a_ticket(self):
        return insert_ticket(self.env, owner='', reporter='santa',
                             summary='Foo', description='Bar',
                             foo='This is a custom field')

    def _create_a_ticket_with_email(self):
        return insert_ticket(self.env, owner='joe@example.org',
                             reporter='santa@example.org',
                             cc='cc1, cc2@example.org', summary='Foo',
                             description='Bar')

    def test_conversions(self):
        conversions = self.mimeview.get_supported_conversions(
            'trac.ticket.Ticket')
        expected = [('rss', 'RSS Feed', 'xml',
                     'trac.ticket.Ticket', 'application/rss+xml', 8,
                     self.ticket_module),
                    ('csv', 'Comma-delimited Text', 'csv',
                     'trac.ticket.Ticket', 'text/csv', 8,
                     self.ticket_module),
                    ('tab', 'Tab-delimited Text', 'tsv',
                     'trac.ticket.Ticket', 'text/tab-separated-values', 8,
                     self.ticket_module)]
        self.assertEqual(expected, list(conversions))

    def test_csv_conversion(self):
        ticket = self._create_a_ticket()
        csv = self.mimeview.convert_content(self.req, 'trac.ticket.Ticket',
                                            ticket, 'csv')
        self.assertEqual(('\xef\xbb\xbf'
                          'id,summary,reporter,owner,description,status,'
                          'keywords,cc\r\n1,Foo,santa,,Bar,,,\r\n',
                          'text/csv;charset=utf-8', 'csv'), csv)

    def test_csv_conversion_with_obfuscation(self):
        ticket = self._create_a_ticket_with_email()
        csv = self.mimeview.convert_content(self.req, 'trac.ticket.Ticket',
                                            ticket, 'csv')
        self.assertEqual(
            ('\xef\xbb\xbf'
             'id,summary,reporter,owner,description,status,keywords,cc\r\n'
             '1,Foo,santa@…,joe@…,Bar,,,cc1 cc2@…\r\n',
             'text/csv;charset=utf-8', 'csv'),
            csv)
        self.req.perm = MockPerm()
        csv = self.mimeview.convert_content(self.req, 'trac.ticket.Ticket',
                                            ticket, 'csv')
        self.assertEqual(
            ('\xef\xbb\xbf'
             'id,summary,reporter,owner,description,status,keywords,cc\r\n'
             '1,Foo,santa@example.org,joe@example.org,Bar,,,'
             'cc1 cc2@example.org\r\n',
             'text/csv;charset=utf-8', 'csv'),
            csv)

    def test_tab_conversion(self):
        ticket = self._create_a_ticket()
        csv = self.mimeview.convert_content(self.req, 'trac.ticket.Ticket',
                                            ticket, 'tab')
        self.assertEqual(('\xef\xbb\xbf'
                          'id\tsummary\treporter\towner\tdescription\tstatus\t'
                          'keywords\tcc\r\n1\tFoo\tsanta\t\tBar\t\t\t\r\n',
                          'text/tab-separated-values;charset=utf-8', 'tsv'),
                         csv)

    def test_tab_conversion_with_obfuscation(self):
        ticket = self._create_a_ticket_with_email()
        csv = self.mimeview.convert_content(self.req, 'trac.ticket.Ticket',
                                            ticket, 'tab')
        self.assertEqual(
            ('\xef\xbb\xbf'
             'id\tsummary\treporter\towner\tdescription\tstatus\tkeywords\t'
             'cc\r\n'
             '1\tFoo\tsanta@…\tjoe@…\tBar\t\t\tcc1 cc2@…\r\n',
             'text/tab-separated-values;charset=utf-8', 'tsv'),
            csv)
        self.req.perm = MockPerm()
        csv = self.mimeview.convert_content(self.req, 'trac.ticket.Ticket',
                                            ticket, 'tab')
        self.assertEqual(
            ('\xef\xbb\xbf'
             'id\tsummary\treporter\towner\tdescription\tstatus\tkeywords\t'
             'cc\r\n'
             '1\tFoo\tsanta@example.org\tjoe@example.org\tBar\t\t\t'
             'cc1 cc2@example.org\r\n',
             'text/tab-separated-values;charset=utf-8', 'tsv'),
            csv)

    def test_rss_conversion(self):
        ticket = self._create_a_ticket()
        content, mimetype, ext = self.mimeview.convert_content(
            self.req, 'trac.ticket.Ticket', ticket, 'rss')
        self.maxDiff = None
        self.assertEqual(("""<?xml version="1.0"?>



<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">

  <channel>
    <title>My Project: Ticket #1: Foo</title>
    <link>http://example.org/trac.cgi/ticket/1</link>
    <description>&lt;p&gt;
Bar
&lt;/p&gt;
</description>
    <language>en-us</language>
    <image>
      <title>My Project</title>
      <url>http://example.org/trac.cgi/chrome/site/your_project_logo.png</url>
      <link>http://example.org/trac.cgi/ticket/1</link>
    </image>
    <generator>Trac %s</generator>

 </channel>
</rss>""" % self.env.trac_version,
                          'application/rss+xml', 'xml'),
                         (content.replace('\r', ''), mimetype, ext))


def test_suite():
    return unittest.makeSuite(TicketConversionTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
