# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#
# FIXME:
# * We need to figure out the encoding used somehow.

from trac import perm, util
from trac.Module import Module
from trac.WikiFormatter import wiki_to_html

import svn.core
import svn.fs
import svn.util

import os
import time
import urllib


class FileCommon(Module):
    CHUNK_SIZE = 4096
    DISP_MAX_FILE_SIZE = 256 * 1024

    # set by the module_factory
    authzperm = None
    fs_ptr = None
    pool = None
    repos = None

    filename = None
    rev = None
    mime_type = None
    last_modified = None
    length = None
    read_func = None

    def render(self, req):
        format = req.args.get('format')
        if format == 'raw':
            self.display_raw(req)
        elif format == 'txt':
            self.mime_type = 'text/plain;charset=utf-8'
            self.display_raw(req)
        else:
            self.display_html(req)

    def display_html(self, req):
        self.log.debug("Displaying file: %s  mime-type: %s" % (self.filename,
                                                               self.mime_type))
        # We don't have to guess if the charset is specified in the
        # svn:mime-type property
        ctpos = self.mime_type.find('charset=')
        if ctpos >= 0:
            charset = self.mime_type[ctpos + 8:]
            self.log.debug("Charset %s selected" % charset)
        else:
            charset = self.env.get_config('trac', 'default_charset', 'iso-8859-15')
        data = util.to_utf8(self.read_func(self.DISP_MAX_FILE_SIZE), charset)

        if len(data) == self.DISP_MAX_FILE_SIZE:
            req.hdf['file.max_file_size_reached'] = 1
            req.hdf['file.max_file_size'] = self.DISP_MAX_FILE_SIZE
            vdata = ' '
        else:
            vdata = self.env.mimeview.display(data, filename=self.filename,
                                              rev=self.rev,
                                              mimetype=self.mime_type)
        req.hdf['file.highlighted_html'] = vdata
        req.display('file.cs')

    def display_raw(self, req):
        req.send_response(200)
        req.send_header('Content-Type', self.mime_type)
        req.send_header('Content-Length', str(self.length))
        req.send_header('Last-Modified',
                        time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                      self.last_modified))
        req.end_headers()
        i = 0
        while 1:
            data = self.read_func(self.CHUNK_SIZE)
            if not data:
                break
            req.write(data)
            i += self.CHUNK_SIZE


class Attachment(FileCommon):

    def get_attachment_parent_link(self):
        if self.attachment_type == 'ticket':
            return ('Ticket #' + self.attachment_id,
                    self.env.href.ticket(self.attachment_id))
        elif self.attachment_type == 'wiki':
            return (self.attachment_id, self.env.href.wiki(self.attachment_id))
        assert 0

    def render(self, req):
        self.perm.assert_permission(perm.WIKI_VIEW)

        self.view_form = 0
        self.attachment_type = req.args.get('type', None)
        self.attachment_id = req.args.get('id', None)
        self.filename = req.args.get('filename', None)
        if self.filename:
            self.filename = os.path.basename(self.filename)

        if not self.attachment_type or not self.attachment_id:
            raise util.TracError('Unknown request')

        if self.filename and len(self.filename) > 0 and \
               req.args.has_key('delete'):
            perm_map = {'ticket': perm.TICKET_ADMIN, 'wiki': perm.WIKI_DELETE}
            self.perm.assert_permission(perm_map[self.attachment_type])
            self.env.delete_attachment(self.db,
                                       self.attachment_type,
                                       self.attachment_id,
                                       self.filename)
            text, link = self.get_attachment_parent_link()
            req.redirect(link)

        if self.filename and len(self.filename) > 0:
            # Send an attachment
            perm_map = {'ticket': perm.TICKET_VIEW, 'wiki': perm.WIKI_VIEW}
            self.perm.assert_permission(perm_map[self.attachment_type])

            self.path = os.path.join(self.env.get_attachments_dir(),
                                     self.attachment_type,
                                     urllib.quote(self.attachment_id),
                                     urllib.quote(self.filename))
            try:
                fd = open(self.path, 'rb')
            except IOError:
                raise util.TracError('Attachment not found')
            
            stat = os.fstat(fd.fileno())
            self.last_modified = time.gmtime(stat[8])
            req.check_modified(stat[8])

            self.length = stat[6]
            self.read_func = lambda x, f=fd: f.read(x)
            self.mime_type = self.env.mimeview.get_mimetype(self.filename) \
                             or 'application/octet-stream'

            self.add_link(req, 'alternate',
                          self.env.href.attachment(self.attachment_type,
                                                   self.attachment_id,
                                                   self.filename, format='txt'),
                          'Plain Text', 'text/plain')
            self.add_link(req, 'alternate',
                          self.env.href.attachment(self.attachment_type,
                                                   self.attachment_id,
                                                   self.filename, format='raw'),
                          'Original Format', self.mime_type)

            perm_map = {'ticket': perm.TICKET_ADMIN, 'wiki': perm.WIKI_DELETE}
            if self.perm.has_permission(perm_map[self.attachment_type]):
                req.hdf['attachment.delete_href'] = '?delete=yes'

        elif req.args.has_key('description') and \
               req.args.has_key('author') and \
               req.args.has_key('attachment') and \
               hasattr(req.args['attachment'], 'file'):

            if req.args.has_key('cancel'):
                req.redirect(self.get_attachment_parent_link()[1])

            # Create a new attachment
            if not self.attachment_type in ['ticket', 'wiki']:
                raise util.TracError('Unknown attachment type')

            perm_map = {'ticket':perm.TICKET_MODIFY, 'wiki': perm.WIKI_MODIFY}
            self.perm.assert_permission (perm_map[self.attachment_type])

            filename = self.env.create_attachment(self.db,
                                                  self.attachment_type,
                                                  self.attachment_id,
                                                  req.args['attachment'],
                                                  req.args.get('description'),
                                                  req.args.get('author'),
                                                  req.remote_addr)
            # Redirect the user to the newly created attachment
            req.redirect(self.env.href.attachment(self.attachment_type,
                                                  self.attachment_id,
                                                  filename))
        else:
            # Display an attachment upload form
            self.view_form = 1

        text, link = self.get_attachment_parent_link()
        self.add_link(req, 'up', link, text)
        req.hdf['title'] = '%s%s: %s' % (
                           self.attachment_type == 'ticket' and '#' or '',
                           self.attachment_id, self.filename)
        req.hdf['file.attachment_parent'] = text
        req.hdf['file.attachment_parent_href'] = link
        if self.view_form:
            req.hdf['attachment.type'] = self.attachment_type
            req.hdf['attachment.id'] = self.attachment_id
            req.hdf['attachment.author'] = util.get_reporter_id(req)
            req.display('attachment.cs')
            return
        req.hdf['file.filename'] = urllib.unquote(self.filename)
        req.hdf['trac.active_module'] = self.attachment_type # Kludge

        FileCommon.render(self, req)


class File(FileCommon):

    def generate_path_links(self, req, rev, rev_specified):
        # FIXME: Browser, Log and File should share implementation of this
        # function.
        list = filter(None, self.path.split('/'))
        self.log.debug("Path links: %s" % list)
        self.filename = list[-1]
        path = '/'
        req.hdf['file.filename'] = list[-1]
        req.hdf['file.path.0'] = 'root'
        if rev_specified:
            req.hdf['file.path.0.url'] = self.env.href.browser(path, rev=rev)
        else:
            req.hdf['file.path.0.url'] = self.env.href.browser(path)
        i = 0
        for part in list[:-1]:
            i = i + 1
            path = path + part + '/'
            req.hdf['file.path.%d' % i] = part
            url = ''
            if rev_specified:
                url = self.env.href.browser(path, rev=rev)
            else:
                url = self.env.href.browser(path)
            req.hdf['file.path.%d.url' % i] = url
            if i == len(list) - 1:
                self.add_link(req, 'up', url, 'Parent directory')

    def render(self, req):
        self.perm.assert_permission(perm.FILE_VIEW)

        self.rev = req.args.get('rev', None)
        self.path = req.args.get('path', '/')
        if not self.rev:
            rev_specified = 0
            self.rev = svn.fs.youngest_rev(self.fs_ptr, self.pool)
        else:
            rev_specified = 1
            try:
                self.rev = int(self.rev)
            except ValueError:
                rev_specified = 0
                self.rev = svn.fs.youngest_rev(self.fs_ptr, self.pool)

        self.authzperm.assert_permission(self.path)
        req.hdf['title'] = self.path

        date = svn.fs.revision_prop(self.fs_ptr, self.rev,
                                    svn.util.SVN_PROP_REVISION_DATE, self.pool)
        date_seconds = svn.util.svn_time_from_cstring(date, self.pool) / 1000000
        self.last_modified = time.gmtime(date_seconds)
        req.check_modified(date_seconds)

        self.generate_path_links(req, self.rev, rev_specified)

        try:
            root = svn.fs.revision_root(self.fs_ptr, self.rev, self.pool)
        except svn.core.SubversionException:
            self.rev = svn.fs.youngest_rev(self.fs_ptr, self.pool)
            root = svn.fs.revision_root(self.fs_ptr, self.rev, self.pool)

        node_type = svn.fs.check_path(root, self.path, self.pool)
        if not node_type in [svn.core.svn_node_dir, svn.core.svn_node_file]:
            self.rev = svn.fs.youngest_rev(self.fs_ptr, self.pool)
            root = svn.fs.revision_root(self.fs_ptr, self.rev, self.pool)
            oh = svn.fs.node_history(root, self.path, self.pool)
            while oh:
                h = oh
                oh = svn.fs.history_prev(h, 0, self.pool)
            history = h
        else:
            history = svn.fs.node_history(root, self.path, self.pool)
            history = svn.fs.history_prev(history, 0, self.pool)
        history_path, history_rev = svn.fs.history_location(history, self.pool);

        if self.rev != history_rev:
            self.rev = history_rev

        author = svn.fs.revision_prop(self.fs_ptr, self.rev,
                                      svn.core.SVN_PROP_REVISION_AUTHOR, self.pool)
        msg = svn.fs.revision_prop(self.fs_ptr, self.rev,
                                   svn.core.SVN_PROP_REVISION_LOG, self.pool)
        msg_html = wiki_to_html(util.wiki_escape_newline(msg), req.hdf, self.env, self.db)
        date = svn.fs.revision_prop(self.fs_ptr, self.rev,
                                    svn.core.SVN_PROP_REVISION_DATE, self.pool)
        sdate = util.svn_date_to_string(date, self.pool)

        req.hdf['file.chgset_href'] = self.env.href.changeset(self.rev)
        req.hdf['file.rev'] = self.rev
        req.hdf['file.rev_author'] = author
        req.hdf['file.rev_date'] = sdate
        req.hdf['file.rev_msg'] = msg_html
        req.hdf['file.path'] = self.path
        req.hdf['file.logurl'] = util.escape(self.env.href.log(self.path,
                                                               rev=self.rev))

        # Try to do an educated guess about the mime-type
        self.mime_type = svn.fs.node_prop (root, self.path,
                                           svn.util.SVN_PROP_MIME_TYPE,
                                           self.pool)
        if not self.mime_type:
            self.mime_type = self.env.mimeview.get_mimetype(filename=self.path) or \
                             'text/plain'
        elif self.mime_type == 'application/octet-stream':
            self.mime_type = self.env.mimeview.get_mimetype(filename=self.path) or \
                             'application/octet-stream'

        self.add_link(req, 'alternate', self.env.href.file(self.path, rev=self.rev, format='raw'),
            'Original Format', self.mime_type)
        self.add_link(req, 'alternate', self.env.href.file(self.path, rev=self.rev, format='txt'),
            'Plain Text', 'text/plain')

        self.length = svn.fs.file_length(root, self.path, self.pool)
        fd = svn.fs.file_contents(root, self.path, self.pool)
        self.read_func = lambda x, f=fd: svn.util.svn_stream_read(f, x)

        FileCommon.render(self, req)
