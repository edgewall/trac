# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2004 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2006 Christian Boos <cboos@neuf.fr>
# Copyright (C) 2006 Matthew Good <trac@matt-good.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import csv
import re
from StringIO import StringIO

from genshi.builder import tag

from trac.config import IntOption
from trac.core import *
from trac.db import get_column_names
from trac.mimeview import Context
from trac.perm import IPermissionRequestor
from trac.resource import Resource, ResourceNotFound
from trac.util import sorted
from trac.util.datefmt import format_datetime, format_time
from trac.util.presentation import Paginator
from trac.util.text import to_unicode, unicode_urlencode
from trac.util.translation import _
from trac.web.api import IRequestHandler, RequestDone
from trac.web.chrome import add_ctxtnav, add_link, add_notice, \
                            add_stylesheet, INavigationContributor, Chrome
from trac.wiki import IWikiSyntaxProvider, WikiParser


class ReportModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IWikiSyntaxProvider)

    items_per_page = IntOption('report', 'items_per_page', 100,
        """Number of tickets displayed per page in ticket reports,
        by default (''since 0.11'')""")

    items_per_page_rss = IntOption('report', 'items_per_page_rss', 0,
        """Number of tickets displayed in the rss feeds for reports
        (''since 0.11'')""")
    
    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'tickets'

    def get_navigation_items(self, req):
        if 'REPORT_VIEW' in req.perm:
            yield ('mainnav', 'tickets', tag.a(_('View Tickets'),
                                               href=req.href.report()))

    # IPermissionRequestor methods  

    def get_permission_actions(self):  
        actions = ['REPORT_CREATE', 'REPORT_DELETE', 'REPORT_MODIFY',  
                   'REPORT_SQL_VIEW', 'REPORT_VIEW']  
        return actions + [('REPORT_ADMIN', actions)]  

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/report(?:/(?:([0-9]+)|-1))?$', req.path_info)
        if match:
            if match.group(1):
                req.args['id'] = match.group(1)
            return True

    def process_request(self, req):
        req.perm.require('REPORT_VIEW')

        # did the user ask for any special report?
        id = int(req.args.get('id', -1))
        action = req.args.get('action', 'view')

        db = self.env.get_db_cnx()

        data = {}
        if req.method == 'POST':
            if action == 'new':
                self._do_create(req, db)
            elif action == 'delete':
                self._do_delete(req, db, id)
            elif action == 'edit':
                self._do_save(req, db, id)
        elif action in ('copy', 'edit', 'new'):
            template = 'report_edit.html'
            data = self._render_editor(req, db, id, action=='copy')
        elif action == 'delete':
            template = 'report_delete.html'
            data = self._render_confirm_delete(req, db, id)
        else:
            template, data, content_type = self._render_view(req, db, id)
            if content_type: # i.e. alternate format
               return template, data, content_type

        if id != -1 or action == 'new':
            add_ctxtnav(req, _('Available Reports'), href=req.href.report())
            add_link(req, 'up', req.href.report(), _('Available Reports'))
        else:
            add_ctxtnav(req, _('Available Reports'))

        # Kludge: only show link to custom query if the query module is actually
        # enabled
        from trac.ticket.query import QueryModule
        if 'TICKET_VIEW' in req.perm and \
                self.env.is_component_enabled(QueryModule):
            add_ctxtnav(req, _('Custom Query'), href=req.href.query())
            data['query_href'] = req.href.query()
        else:
            data['query_href'] = None

        add_stylesheet(req, 'common/css/report.css')
        return template, data, None

    # Internal methods

    def _do_create(self, req, db):
        req.perm.require('REPORT_CREATE')

        if 'cancel' in req.args:
            req.redirect(req.href.report())

        title = req.args.get('title', '')
        query = req.args.get('query', '')
        description = req.args.get('description', '')
        cursor = db.cursor()
        cursor.execute("INSERT INTO report (title,query,description) "
                       "VALUES (%s,%s,%s)", (title, query, description))
        id = db.get_last_id(cursor, 'report')
        db.commit()
        add_notice(req, _('The report has been created.'))
        req.redirect(req.href.report(id))

    def _do_delete(self, req, db, id):
        req.perm.require('REPORT_DELETE')

        if 'cancel' in req.args:
            req.redirect(req.href.report(id))

        cursor = db.cursor()
        cursor.execute("DELETE FROM report WHERE id=%s", (id,))
        db.commit()
        add_notice(req, _('The report {%(id)d} has been deleted.', id=id))
        req.redirect(req.href.report())

    def _do_save(self, req, db, id):
        """Save report changes to the database"""
        req.perm.require('REPORT_MODIFY')

        if 'cancel' not in req.args:
            title = req.args.get('title', '')
            query = req.args.get('query', '')
            description = req.args.get('description', '')
            cursor = db.cursor()
            cursor.execute("UPDATE report SET title=%s,query=%s,description=%s "
                           "WHERE id=%s", (title, query, description, id))
            db.commit()
            add_notice(req, _('Your changes have been saved.'))
        req.redirect(req.href.report(id))

    def _render_confirm_delete(self, req, db, id):
        req.perm.require('REPORT_DELETE')

        cursor = db.cursor()
        cursor.execute("SELECT title FROM report WHERE id=%s", (id,))
        for title, in cursor:
            return {'title': _('Delete Report {%(num)s} %(title)s', num=id,
                               title=title),
                    'action': 'delete',
                    'report': {'id': id, 'title': title}}
        else:
            raise TracError(_('Report %(num)s does not exist.', num=id),
                            _('Invalid Report Number'))

    def _render_editor(self, req, db, id, copy):
        if id != -1:
            req.perm.require('REPORT_MODIFY')
            cursor = db.cursor()
            cursor.execute("SELECT title,description,query FROM report "
                           "WHERE id=%s", (id,))
            for title, description, query in cursor:
                break
            else:
                raise TracError(_('Report %(num)s does not exist.', num=id),
                                _('Invalid Report Number'))
        else:
            req.perm.require('REPORT_CREATE')
            title = description = query = ''

        # an explicitly given 'query' parameter will override the saved query
        query = req.args.get('query', query)

        if copy:
            title += ' (copy)'

        if copy or id == -1:
            data = {'title': _('Create New Report'),
                    'action': 'new',
                    'error': None}
        else:
            data = {'title': _('Edit Report {%(num)d} %(title)s', num=id,
                               title=title),
                    'action': 'edit',
                    'error': req.args.get('error')}

        data['report'] = {'id': id, 'title': title,
                          'sql': query, 'description': description}
        return data

    def _render_view(self, req, db, id):
        """Retrieve the report results and pre-process them for rendering."""
        try:
            args = self.get_var_args(req)
        except ValueError,e:
            raise TracError(_('Report failed: %(error)s', error=e))

        if id == -1:
            # If no particular report was requested, display
            # a list of available reports instead
            title = _('Available Reports')
            sql = ("SELECT id AS report, title, 'report' as _realm "
                   "FROM report ORDER BY report")
            description = _('This is a list of available reports.')
        else:
            cursor = db.cursor()
            cursor.execute("SELECT title,query,description from report "
                           "WHERE id=%s", (id,))
            for title, sql, description in cursor:
                break
            else:
                raise ResourceNotFound(
                    _('Report %(num)s does not exist.', num=id),
                    _('Invalid Report Number'))

        # If this is a saved custom query. redirect to the query module
        #
        # A saved query is either an URL query (?... or query:?...),
        # or a query language expression (query:...).
        #
        # It may eventually contain newlines, for increased clarity.
        #
        query = ''.join([line.strip() for line in sql.splitlines()])
        if query and (query[0] == '?' or query.startswith('query:?')):
            query = query[0] == '?' and query or query[6:]
            report_id = 'report=%s' % id
            if 'report=' in query:
                if not report_id in query:
                    err = _('When specified, the report number should be '
                            '"%(num)s".', num=id)
                    req.redirect(req.href.report(id, action='edit', error=err))
            else:
                if query[-1] != '?':
                    query += '&'
                query += report_id
            req.redirect(req.href.query() + query)
        elif query.startswith('query:'):
            try:
                from trac.ticket.query import Query, QuerySyntaxError
                query = Query.from_string(self.env, query[6:], report=id)
                req.redirect(query.get_href(req))
            except QuerySyntaxError, e:
                req.redirect(req.href.report(id, action='edit',
                                             error=to_unicode(e)))

        format = req.args.get('format')
        if format == 'sql':
            self._send_sql(req, id, title, description, sql)

        if id > 0:
            title = '{%i} %s' % (id, title)

        report_resource = Resource('report', id)
        req.perm.require('REPORT_VIEW', report_resource)
        context = Context.from_request(req, report_resource)
        data = {'action': 'view',
                'report': {'id': id, 'resource': report_resource},
                'context': context,
                'title': title, 'description': description,
                'args': args, 'message': None, 'paginator':None}

        page = int(req.args.get('page', '1'))
        limit = {'rss': self.items_per_page_rss,
                 'csv': 0, 'tab': 0}.get(format, self.items_per_page)
        print repr(limit)
        offset = (page - 1) * limit
        user = req.args.get('USER', None)

        try:
            cols, results, num_items = self.execute_paginated_report(
                    req, db, id, sql, args, limit, offset)
            results = [list(row) for row in results]
            numrows = len(results)

        except Exception, e:
            db.rollback()
            data['message'] = _('Report execution failed: %(error)s',
                                error=to_unicode(e))
            return 'report_view.html', data, None
        paginator = None
        if id != -1 and limit > 0:
            asc = req.args.get('asc', None)
            sort_col = req.args.get('sort', None)
            paginator = Paginator(results, page - 1, limit, num_items)
            data['paginator'] = paginator
            if paginator.has_next_page:
                next_href = req.href.report(id, asc=asc, sort=sort_col,
                                            page=page + 1, **args)
                add_link(req, 'next', next_href, _('Next Page'))
            if paginator.has_previous_page:
                prev_href = req.href.report(id, asc=asc, sort=sort_col,
                                            page=page - 1, **args)
                add_link(req, 'prev', prev_href, _('Previous Page'))

            pagedata = []
            shown_pages = paginator.get_shown_pages(21)
            for p in shown_pages:
                pagedata.append([req.href.report(id, asc=asc, sort=sort_col, 
                                                 page=p, **args),
                                 None, str(p), _('Page %(num)d', num=p)])          
            fields = ['href', 'class', 'string', 'title']
            paginator.shown_pages = [dict(zip(fields, p)) for p in pagedata]
            paginator.current_page = {'href': None, 'class': 'current',
                                    'string': str(paginator.page + 1),
                                    'title': None}
            numrows = paginator.num_items

        sort_col = req.args.get('sort', '')
        asc = req.args.get('asc', 1)
        asc = bool(int(asc)) # string '0' or '1' to int/boolean

        # Place retrieved columns in groups, according to naming conventions
        #  * _col_ means fullrow, i.e. a group with one header
        #  * col_ means finish the current group and start a new one
        header_groups = [[]]
        for idx, col in enumerate(cols):
            header = {
                'col': col,
                'title': col.strip('_').capitalize(),
                'hidden': False,
                'asc': False
            }

            if col == sort_col:
                header['asc'] = asc
                if not paginator:
                    # this dict will have enum values for sorting
                    # and will be used in sortkey(), if non-empty:
                    sort_values = {}
                    if sort_col in ['status', 'resolution', 'priority', 
                                    'severity']:
                        # must fetch sort values for that columns
                        # instead of comparing them as strings
                        if not db:
                            db = self.env.get_db_cnx()
                        cursor = db.cursor()
                        cursor.execute("SELECT name," + 
                                       db.cast('value', 'int') + 
                                       " FROM enum WHERE type=%s", (sort_col,))
                        for name, value in cursor:
                            sort_values[name] = value

                    def sortkey(row):
                        val = row[idx]
                        # check if we have sort_values, then use them as keys.
                        if sort_values:
                            return sort_values.get(val)
                        # otherwise, continue with string comparison:
                        if isinstance(val, basestring):
                            val = val.lower()
                        return val
                    results = sorted(results, key=sortkey, reverse=(not asc))

            header_group = header_groups[-1]

            if col.startswith('__') and col.endswith('__'): # __col__
                header['hidden'] = True
            elif col[0] == '_' and col[-1] == '_':          # _col_
                header_group = []
                header_groups.append(header_group)
                header_groups.append([])
            elif col[0] == '_':                             # _col
                header['hidden'] = True
            elif col[-1] == '_':                            # col_
                header_groups.append([])
            header_group.append(header)

        # Structure the rows and cells:
        #  - group rows according to __group__ value, if defined
        #  - group cells the same way headers are grouped
        row_groups = []
        prev_group_value = None
        for row_idx, result in enumerate(results):
            col_idx = 0
            cell_groups = []
            row = {'cell_groups': cell_groups}
            realm = 'ticket'
            email_cells = []
            for header_group in header_groups:
                cell_group = []
                for header in header_group:
                    value = unicode(result[col_idx] or '')
                    cell = {'value': value, 'header': header, 'index': col_idx}
                    col = header['col']
                    col_idx += 1
                    # Detect and create new group
                    if col == '__group__' and value != prev_group_value:
                        prev_group_value = value
                        # Brute force handling of email in group by header
                        row_groups.append(
                            (Chrome(self.env).format_author(req, value), []) )
                    # Other row properties
                    row['__idx__'] = row_idx
                    if col in ('__style__', '__color__',
                               '__fgcolor__', '__bgcolor__'):
                        row[col] = value
                    if col in ('report', 'ticket', 'id', '_id'):
                        row['id'] = value
                    # Special casing based on column name
                    col = col.strip('_')
                    if col in ('reporter', 'cc', 'owner'):
                        email_cells.append(cell)
                    elif col == 'realm':
                        realm = value
                    cell_group.append(cell)
                cell_groups.append(cell_group)
            resource = Resource(realm, row.get('id'))
            # FIXME: for now, we still need to hardcode the realm in the action
            if resource.realm.upper()+'_VIEW' not in req.perm(resource):
                continue
            if email_cells:
                for cell in email_cells:
                    emails = Chrome(self.env).format_emails(context(resource),
                                                            cell['value'])
                    result[cell['index']] = cell['value'] = emails
            row['resource'] = resource
            if row_groups:
                row_group = row_groups[-1][1]
            else:
                row_group = []
                row_groups = [(None, row_group)]
            row_group.append(row)

        # Get the email addresses of all known users
        email_map = {}
        if Chrome(self.env).show_email_addresses:
            for username, name, email in self.env.get_known_users():
                if email:
                    email_map[username] = email

        data.update({'header_groups': header_groups,
                     'row_groups': row_groups,
                     'numrows': numrows,
                     'sorting_enabled': len(row_groups)==1,
                     'email_map': email_map})

        if id and id != -1:
            self.add_alternate_links(req, args)

        if format == 'rss':
            data['context'] = Context.from_request(req, report_resource,
                                                   absurls=True)
            return 'report.rss', data, 'application/rss+xml'
        elif format == 'csv':
            filename = id and 'report_%s.csv' % id or 'report.csv'
            self._send_csv(req, cols, results, mimetype='text/csv',
                           filename=filename)
        elif format == 'tab':
            filename = id and 'report_%s.tsv' % id or 'report.tsv'
            self._send_csv(req, cols, results, '\t',
                           mimetype='text/tab-separated-values',
                           filename=filename)
        else:
            if id != -1:
                # reuse the session vars of the query module so that
                # the query navigation links on the ticket can be used to 
                # navigate report results as well
                try:
                    req.session['query_tickets'] = \
                        ' '.join([str(int(row['id']))
                                  for rg in row_groups for row in rg[1]])
                    req.session['query_href'] = \
                        req.href.report(id, asc=req.args.get('asc', None),
                                        sort=req.args.get('sort', None),
                                        page=page, **args)
                    # Kludge: we have to clear the other query session
                    # variables, but only if the above succeeded 
                    for var in ('query_constraints', 'query_time'):
                        if var in req.session:
                            del req.session[var]
                except (ValueError, KeyError):
                    pass
            return 'report_view.html', data, None

    def add_alternate_links(self, req, args):
        params = args.copy()
        if 'sort' in req.args:
            params['sort'] = req.args['sort']
        if 'asc' in req.args:
            params['asc'] = req.args['asc']
        href = ''
        if params:
            href = '&' + unicode_urlencode(params)
        add_link(req, 'alternate', '?format=rss' + href, _('RSS Feed'),
                 'application/rss+xml', 'rss')
        add_link(req, 'alternate', '?format=csv' + href,
                 _('Comma-delimited Text'), 'text/plain')
        add_link(req, 'alternate', '?format=tab' + href,
                 _('Tab-delimited Text'), 'text/plain')
        if 'REPORT_SQL_VIEW' in req.perm:
            add_link(req, 'alternate', '?format=sql', _('SQL Query'),
                     'text/plain')

    def execute_report(self, req, db, id, sql, args):
        """Execute given sql report (0.10 backward compatibility method)
        
        :see: ``execute_paginated_report``
        """
        return self.execute_paginated_report(req, db, id, sql, args)[:2]

    def execute_paginated_report(self, req, db, id, sql, args, 
                                 limit=0, offset=0):
        sql, args = self.sql_sub_vars(sql, args, db)
        if not sql:
            raise TracError(_('Report %(num)s has no SQL query.', num=id))
        self.log.debug('Executing report with SQL "%s"' % sql)
        self.log.debug('Request args: %r' % req.args)
        cursor = db.cursor()

        num_items = 0
        if id != -1 and limit > 0:
            # The number of tickets is obtained.
            count_sql = 'SELECT COUNT(*) FROM (' + sql + ') AS tab'
            cursor.execute(count_sql, args)
            self.log.debug("Query SQL(Get num items): " + count_sql)
            for row in cursor:
                pass
            num_items = row[0]
    
            # The column name is obtained.
            get_col_name_sql = 'SELECT * FROM ( ' + sql + ' ) AS tab LIMIT 1'
            cursor.execute(get_col_name_sql, args)
            self.env.log.debug("Query SQL(Get col names): " + get_col_name_sql)
            cols = get_column_names(cursor)

            sort_col = req.args.get('sort', '')
            self.log.debug("Columns %r, Sort column %s" % (cols, sort_col))
            order_cols = []
            if sort_col:
                if '__group__' in cols:
                    order_cols.append('__group__')
                if sort_col in cols:
                    order_cols.append(sort_col)
                else:
                    raise TracError(_('Query parameter "sort=%(sort_col)s" '
                                      ' is invalid', sort_col=sort_col))

            # The report-query results is obtained
            asc = req.args.get('asc', '1')
            asc_str = asc == '1' and 'ASC' or 'DESC'
            order_by = ''
            if len(order_cols) != 0:
                order = ', '.join(order_cols)
                order_by = " ".join([' ORDER BY', order, asc_str])
            sql = " ".join(['SELECT * FROM (', sql, ') AS tab', order_by])
            sql =" ".join([sql, 'LIMIT', str(limit), 'OFFSET', str(offset)])
            self.log.debug("Query SQL: " + sql)
        cursor.execute(sql, args)
        # FIXME: fetchall should probably not be used.
        info = cursor.fetchall() or []
        cols = get_column_names(cursor)

        db.rollback()

        return cols, info, num_items

    def get_var_args(self, req):
        report_args = {}
        for arg in req.args.keys():
            if not arg.isupper():
                continue
            report_args[arg] = req.args.get(arg)

        # Set some default dynamic variables
        if 'USER' not in report_args:
            report_args['USER'] = req.authname

        return report_args

    def sql_sub_vars(self, sql, args, db=None):
        if db is None:
            db = self.env.get_db_cnx()
        values = []
        def add_value(aname):
            try:
                arg = args[aname]
            except KeyError:
                raise TracError(_("Dynamic variable '%(name)s' not defined.",
                                  name='$%s' % aname))
            values.append(arg)

        var_re = re.compile("[$]([A-Z]+)")

        # simple parameter substitution outside literal
        def repl(match):
            add_value(match.group(1))
            return '%s'

        # inside a literal break it and concatenate with the parameter
        def repl_literal(expr):
            parts = var_re.split(expr[1:-1])
            if len(parts) == 1:
                return expr
            params = parts[1::2]
            parts = ["'%s'" % p for p in parts]
            parts[1::2] = ['%s'] * len(params)
            for param in params:
                add_value(param)
            return db.concat(*parts)

        sql_io = StringIO()

        # break SQL into literals and non-literals to handle replacing
        # variables within them with query parameters
        for expr in re.split("('(?:[^']|(?:''))*')", sql):
            if expr.startswith("'"):
                sql_io.write(repl_literal(expr))
            else:
                sql_io.write(var_re.sub(repl, expr))
        return sql_io.getvalue(), values

    def _send_csv(self, req, cols, rows, sep=',', mimetype='text/plain',
                  filename=None):
        def iso_time(t):
            return format_time(t, 'iso8601')

        def iso_datetime(dt):
            return format_datetime(dt, 'iso8601')

        def string(value):
            return unicode(value or '')
        
        col_conversions = {
            'time': iso_time,
            'datetime': iso_datetime,
            'changetime': iso_datetime,
            'date': iso_datetime,
            'created': iso_datetime,
            'modified': iso_datetime,
        }

        converters = [col_conversions.get(c.strip('_'), string) for c in cols]

        out = StringIO()
        writer = csv.writer(out, delimiter=sep)
        writer.writerow([unicode(c).encode('utf-8') for c in cols])
        for row in rows:
            row = list(row)
            for i in xrange(len(row)):
                row[i] = converters[i](row[i]).encode('utf-8')
            writer.writerow(row)
        data = out.getvalue()

        req.send_response(200)
        req.send_header('Content-Type', mimetype + ';charset=utf-8')
        req.send_header('Content-Length', len(data))
        if filename:
            req.send_header('Content-Disposition', 'filename=' + filename)
        req.end_headers()
        req.write(data)
        raise RequestDone

    def _send_sql(self, req, id, title, description, sql):
        req.perm.require('REPORT_SQL_VIEW')

        out = StringIO()
        out.write('-- ## %s: %s ## --\n\n' % (id, title))
        if description:
            out.write('-- %s\n\n' % '\n-- '.join(description.splitlines()))
        out.write(sql)
        data = out.getvalue()

        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.send_header('Content-Length', len(data))
        if id:
            req.send_header('Content-Disposition',
                            'filename=report_%s.sql' % id)
        req.end_headers()
        req.write(data)
        raise RequestDone
        
    # IWikiSyntaxProvider methods
    
    def get_link_resolvers(self):
        yield ('report', self._format_link)

    def get_wiki_syntax(self):
        yield (r"!?\{(?P<it_report>%s\s*)\d+\}" % WikiParser.INTERTRAC_SCHEME,
               lambda x, y, z: self._format_link(x, 'report', y[1:-1], y, z))

    def _format_link(self, formatter, ns, target, label, fullmatch=None):
        intertrac = formatter.shorthand_intertrac_helper(ns, target, label,
                                                         fullmatch)
        if intertrac:
            return intertrac
        report, args, fragment = formatter.split_link(target)
        return tag.a(label, href=formatter.href.report(report) + args,
                     class_='report')
