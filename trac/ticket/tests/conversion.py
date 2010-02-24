import os
import unittest

from trac import __version__ as TRAC_VERSION
from trac.test import EnvironmentStub, Mock
from trac.ticket.model import Ticket
from trac.ticket.web_ui import TicketModule
from trac.mimeview.api import Mimeview
from trac.web.href import Href


class TicketConversionTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.config.set('trac', 'templates_dir',
                            os.path.join(os.path.dirname(self.env.path),
                                         'templates'))
        self.ticket_module = TicketModule(self.env)
        self.mimeview = Mimeview(self.env)
        self.req = Mock(base_path='/trac.cgi', path_info='',
                        href=Href('/trac.cgi'), chrome={'logo': {}},
                        abs_href=Href('http://example.org/trac.cgi'),
                        environ={}, perm=[], authname='-', args={}, tz=None,
                        locale='', session=None, form_token=None)

    def tearDown(self):
        self.env.reset_db()

    def _create_a_ticket(self):
        # 1. Creating ticket
        ticket = Ticket(self.env)
        ticket['reporter'] = 'santa'
        ticket['summary'] = 'Foo'
        ticket['description'] = 'Bar'
        ticket['foo'] = 'This is a custom field'
        ticket.insert()
        return ticket

    def test_conversions(self):
        conversions = self.mimeview.get_supported_conversions(
            'trac.ticket.Ticket')
        expected = sorted([('csv', 'Comma-delimited Text', 'csv',
                           'trac.ticket.Ticket', 'text/csv', 8,
                           self.ticket_module),
                          ('tab', 'Tab-delimited Text', 'tsv',
                           'trac.ticket.Ticket', 'text/tab-separated-values', 8,
                           self.ticket_module),
                           ('rss', 'RSS Feed', 'xml',
                            'trac.ticket.Ticket', 'application/rss+xml', 8,
                            self.ticket_module)],
                          key=lambda i: i[-1], reverse=True)
        self.assertEqual(expected, conversions)

    def test_csv_conversion(self):
        ticket = self._create_a_ticket()
        csv = self.mimeview.convert_content(self.req, 'trac.ticket.Ticket',
                                            ticket, 'csv')
        self.assertEqual((u'id,summary,reporter,owner,description,status,'
                          'keywords,cc\r\n1,Foo,santa,,Bar,,,\r\n',
                          'text/csv;charset=utf-8', 'csv'), csv)


    def test_tab_conversion(self):
        ticket = self._create_a_ticket()
        csv = self.mimeview.convert_content(self.req, 'trac.ticket.Ticket',
                                            ticket, 'tab')
        self.assertEqual((u'id\tsummary\treporter\towner\tdescription\tstatus\t'
                          'keywords\tcc\r\n1\tFoo\tsanta\t\tBar\t\t\t\r\n',
                          'text/tab-separated-values;charset=utf-8', 'tsv'),
                         csv)

    def test_rss_conversion(self):
        ticket = self._create_a_ticket()
        content, mimetype, ext = self.mimeview.convert_content(
            self.req, 'trac.ticket.Ticket', ticket, 'rss')
        self.assertEqual(("""<?xml version="1.0"?>
<rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
  <channel>
    <title>My Project: Ticket #1: Foo</title>
    <link>http://example.org/trac.cgi/ticket/1</link>
    <description>&lt;p&gt;
Bar
&lt;/p&gt;
</description>
    <language>en-us</language>
    <generator>Trac %s</generator>
 </channel>
</rss>""" % (TRAC_VERSION),
                          'application/rss+xml', 'xml'),
                         (content.replace('\r', ''), mimetype, ext))


def suite():
    return unittest.makeSuite(TicketConversionTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
