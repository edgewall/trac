# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004 Edgewall Software
# Copyright (C) 2003, 2004 Jonas Borgström <jonas@edgewall.com>
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

import os
import sys
import time
import urllib
from xml.sax import saxutils

import svn

import perm
import util
import Module
from WikiFormatter import wiki_to_html

class FileCommon(Module.Module):
    CHUNK_SIZE = 4096
    DISP_MAX_FILE_SIZE = 256 * 1024

    filename = None
    rev = None
    mime_type = None

    def render (self):
        self.perm.assert_permission (perm.FILE_VIEW)

    def display(self):
        self.env.log.debug("Displaying file: %s  mime-type: %s" % (self.filename,
                                                            self.mime_type))
        # We don't have to guess if the charset is specified in the
        # svn:mime-type property
        ctpos = self.mime_type.find('charset=')
        if ctpos >= 0:
            charset = self.mime_type[ctpos + 8:]
            self.env.log.debug("Charset %s selected" % charset)
        else:
            charset = self.env.get_config('trac', 'default_charset', 'iso-8859-15')
        data = util.to_utf8(self.read_func(self.DISP_MAX_FILE_SIZE), charset)

        if len(data) == self.DISP_MAX_FILE_SIZE:
            self.req.hdf.setValue('file.max_file_size_reached', '1')
            self.req.hdf.setValue('file.max_file_size', str(self.DISP_MAX_FILE_SIZE))
            vdata = ' '
        else:
            vdata = self.env.mimeview.display(data, filename=self.filename,
                                              rev=self.rev,
                                              mimetype=self.mime_type)
        self.req.hdf.setValue('file.highlighted_html', vdata)
        self.req.display('file.cs')

    def display_raw(self):
        self.req.send_response(200)
        self.req.send_header('Content-Type', self.mime_type)
        self.req.send_header('Content-Length', str(self.length))
        self.req.send_header('Last-Modified', self.last_modified)
        self.req.send_header('Pragma', 'no-cache')
        self.req.send_header('Expires', 'Mon, 26 Jul 1997 05:00:00 GMT')
        self.req.send_header('Cache-Control',
                             'no-store, no-cache, must-revalidate, max-age=0')
        self.req.send_header('Cache-Control', 'post-check=0, pre-check=0')
        self.req.end_headers()
        i = 0
        while 1:
            data = self.read_func(self.CHUNK_SIZE)
            if not data:
                break
            self.req.write(data)
            i += self.CHUNK_SIZE

    def display_txt(self):
        self.mime_type = 'text/plain;charset=utf-8'
        self.display_raw()

class Attachment(FileCommon):

    def get_attachment_parent_link(self):
        if self.attachment_type == 'ticket':
            return ('Ticket #' + self.attachment_id,
                    self.env.href.ticket(int(self.attachment_id)))
        elif self.attachment_type == 'wiki':
            return (self.attachment_id,
                    self.env.href.wiki(self.attachment_id))
        assert 0

    def render(self):
        FileCommon.render(self)
        self.view_form = 0
        self.attachment_type = self.args.get('type', None)
        self.attachment_id = self.args.get('id', None)
        self.filename = self.args.get('filename', None)
        if self.filename:
            self.filename = os.path.basename(self.filename)

        if not self.attachment_type or not self.attachment_id:
            raise util.TracError('Unknown request')

        if self.filename and len(self.filename) > 0 and \
               self.args.has_key('delete'):
            self.perm.assert_permission (perm.TRAC_ADMIN)
            self.env.delete_attachment(self.db,
                                       self.attachment_type,
                                       self.attachment_id,
                                       self.filename)
            text, link = self.get_attachment_parent_link()
            self.req.redirect(link)

        if self.filename and len(self.filename) > 0:
            # Send an attachment
            perm_map = {'ticket':perm.TICKET_VIEW, 'wiki': perm.WIKI_VIEW}
            self.perm.assert_permission (perm_map[self.attachment_type])

            self.path = os.path.join(self.env.get_attachments_dir(),
                                     self.attachment_type,
                                     urllib.quote(self.attachment_id),
                                     urllib.quote(self.filename))
            try:
                fd = open(self.path, 'rb')
            except IOError:
                raise util.TracError('Attachment not found')
            
            stat = os.fstat(fd.fileno())
            self.length = stat[6]
            self.last_modified = time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                               time.gmtime(stat[8]))
            self.read_func = lambda x, f=fd: f.read(x)
            self.mime_type = self.env.mimeview.get_mimetype(self.filename) \
                             or 'application/octet-stream'

            self.add_link('alternate',
                          self.env.href.attachment(self.attachment_type,
                                                   self.attachment_id,
                                                   self.filename, 'txt'),
                'Plain Text', 'text/plain')
            self.add_link('alternate',
                          self.env.href.attachment(self.attachment_type,
                                                   self.attachment_id,
                                                   self.filename, 'raw'),
                'Original Format', self.mime_type)

            return

        if self.args.has_key('description') and \
               self.args.has_key('author') and \
               self.args.has_key('attachment') and \
               hasattr(self.args['attachment'], 'file'):

            if self.args.has_key('cancel'):
                self.req.redirect(self.get_attachment_parent_link()[1])

            # Create a new attachment
            if not self.attachment_type in ['ticket', 'wiki']:
                raise util.TracError('Unknown attachment type')

            perm_map = {'ticket':perm.TICKET_MODIFY, 'wiki': perm.WIKI_MODIFY}
            self.perm.assert_permission (perm_map[self.attachment_type])

            filename = self.env.create_attachment(self.db,
                                                  self.attachment_type,
                                                  self.attachment_id,
                                                  self.args['attachment'],
                                                  self.args.get('description'),
                                                  self.args.get('author'),
                                                  self.req.remote_addr)
            # Redirect the user to the newly created attachment
            self.req.redirect(self.env.href.attachment(self.attachment_type,
                                                       self.attachment_id,
                                                       filename))
        else:
            # Display an attachment upload form
            self.view_form = 1

    def display(self):
        text, link = self.get_attachment_parent_link()
        self.add_link('up', link, text)
        self.req.hdf.setValue('title', '%s%s: %s' % (
                              self.attachment_type == 'ticket' and '#' or '',
                              self.attachment_id, self.filename))
        self.req.hdf.setValue('file.attachment_parent', text)
        self.req.hdf.setValue('file.attachment_parent_href', link)
        if self.view_form:
            self.req.hdf.setValue('attachment.type', self.attachment_type)
            self.req.hdf.setValue('attachment.id', self.attachment_id)
            self.req.hdf.setValue('attachment.author', util.get_reporter_id(self.req))
            self.req.display('attachment.cs')
            return
        self.req.hdf.setValue('file.filename', urllib.unquote(self.filename))
        self.req.hdf.setValue('trac.active_module', self.attachment_type) # Kludge
        FileCommon.display(self)


class File(FileCommon):

    def generate_path_links(self, rev, rev_specified):
        # FIXME: Browser, Log and File should share implementation of this
        # function.
        list = self.path.split('/')
        self.filename = list[-1]
        path = '/'
        self.req.hdf.setValue('file.filename', list[-1])
        self.req.hdf.setValue('file.path.0', 'root')
        if rev_specified:
            self.req.hdf.setValue('file.path.0.url' , self.env.href.browser(path,
                                                                            rev))
        else:
            self.req.hdf.setValue('file.path.0.url' , self.env.href.browser(path))
        i = 0
        for part in list[:-1]:
            i = i + 1
            if part == '':
                continue
            path = path + part + '/'
            self.req.hdf.setValue('file.path.%d' % i, part)
            url = ''
            if rev_specified:
                url = self.env.href.browser(path, rev)
            else:
                url = self.env.href.browser(path)
            self.req.hdf.setValue('file.path.%d.url' % i, url)
            if i == len(list) - 1:
                self.add_link('up', url, 'Parent directory')

    def display(self):
        self.authzperm.assert_permission(self.path)
        self.req.hdf.setValue('title', self.path)
        FileCommon.display(self)

    def render(self):
        FileCommon.render(self)

        self.rev = self.args.get('rev', None)
        self.path = self.args.get('path', '/')
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

        self.generate_path_links(self.rev, rev_specified)

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
        msg_html = wiki_to_html(util.wiki_escape_newline(msg), self.req.hdf, self.env, self.db)
        date = svn.fs.revision_prop(self.fs_ptr, self.rev,
                                    svn.core.SVN_PROP_REVISION_DATE, self.pool)
        sdate = util.svn_date_to_string(date, self.pool)

        self.req.hdf.setValue('file.chgset_href', self.env.href.changeset(self.rev))
        self.req.hdf.setValue('file.rev', str(self.rev))
        self.req.hdf.setValue('file.rev_author', str(author))
        self.req.hdf.setValue('file.rev_date', sdate)
        self.req.hdf.setValue('file.rev_msg', msg_html)
        self.req.hdf.setValue('file.path', self.path)
        self.req.hdf.setValue('file.logurl',
            saxutils.escape(self.env.href.log(self.path, self.rev)))

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

        self.add_link('alternate', self.env.href.file(self.path, self.rev, 'raw'),
            'Original Format', self.mime_type)
        self.add_link('alternate', self.env.href.file(self.path, self.rev, 'txt'),
            'Plain Text', 'text/plain')

        self.length = svn.fs.file_length(root, self.path, self.pool)
        date = svn.fs.revision_prop(self.fs_ptr, self.rev,
                                svn.util.SVN_PROP_REVISION_DATE, self.pool)
        date_seconds = svn.util.svn_time_from_cstring(date, self.pool) / 1000000
        self.last_modified = time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                      time.gmtime(date_seconds))
        fd = svn.fs.file_contents(root, self.path, self.pool)
        self.read_func = lambda x, f=fd: svn.util.svn_stream_read(f, x)
