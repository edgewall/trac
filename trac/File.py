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
import StringIO
import mimetypes

import svn

import perm
import util
from Module import Module
from Wiki import wiki_to_html

class FileCommon(Module):
    CHUNK_SIZE = 4096
    DISP_MAX_FILE_SIZE = 256 * 1024

    filename = None
    mime_type = None
    def render (self):
        self.perm.assert_permission (perm.FILE_VIEW)

    def display(self):
        self.env.log.debug("Displaying file: %s  mime-type: %s" % (self.filename,
                                                            self.mime_type))
        data = util.to_utf8(self.read_func(self.DISP_MAX_FILE_SIZE))
        
        if len(data) == self.DISP_MAX_FILE_SIZE:
            self.req.hdf.setValue('file.max_file_size_reached', '1')
            self.req.hdf.setValue('file.max_file_size', str(self.DISP_MAX_FILE_SIZE))
            vdata = ' '
        else:
            vdata = self.env.mimeview.display(data, filename=self.filename,
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

    def display_text(self):
        self.mime_type = 'text/plain'
        self.display_raw()
    
class Attachment(FileCommon):
    def get_attachment_parent_link(self):
        if self.attachment_type == 'ticket':
            return ('#' + self.attachment_id,
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
                                     self.attachment_id,
                                     self.filename)
            try:
                fd = open(self.path, 'rb')
            except IOError:
                raise util.TracError('Attachment not found')

            stat = os.fstat(fd.fileno())
            self.length = stat[6]
            self.last_modified = time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                               time.gmtime(stat[8]))
            self.read_func = lambda x, f=fd: f.read(x)
            return

        if self.args.has_key('description') and \
               self.args.has_key('author') and \
               self.args.has_key('attachment') and \
               hasattr(self.args['attachment'], 'file'):
            
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
        self.req.hdf.setValue('file.attachment_parent', text)
        self.req.hdf.setValue('file.attachment_parent_href', link)
        if self.view_form:
            self.req.hdf.setValue('attachment.type', self.attachment_type)
            self.req.hdf.setValue('attachment.id', self.attachment_id)
            self.req.display('attachment.cs')
            return
        self.req.hdf.setValue('file.rawurl', 
                              self.env.href.attachment(self.attachment_type,
                                                       self.attachment_id,
                                                       self.filename,
                                                       'raw'))
        self.req.hdf.setValue('file.texturl', 
                              self.env.href.attachment(self.attachment_type,
                                                       self.attachment_id,
                                                       self.filename,
                                                       'text'))
        self.req.hdf.setValue('file.filename', self.filename)
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
                break
            path = path + part + '/'
            self.req.hdf.setValue('file.path.%d' % i, part)
            if rev_specified:
                self.req.hdf.setValue('file.path.%d.url' % i,
                                      self.env.href.browser(path, rev))
            else:
                self.req.hdf.setValue('file.path.%d.url' % i,
                                      self.env.href.browser(path))

    def display(self):
        FileCommon.display(self)

    def render(self):
        FileCommon.render(self)
        
        rev = self.args.get('rev', None)
        self.path = self.args.get('path', '/')
        if not rev:
            rev_specified = 0
            rev = svn.fs.youngest_rev(self.fs_ptr, self.pool)
        else:
            rev_specified = 1
            try:
                rev = int(rev)
            except ValueError:
                rev_specified = 0
                rev = svn.fs.youngest_rev(self.fs_ptr, self.pool)

        self.generate_path_links(rev, rev_specified)

        root = svn.fs.revision_root(self.fs_ptr, rev, self.pool)
        history = svn.fs.node_history(root, self.path, self.pool)
        history = svn.fs.history_prev(history, 0, self.pool)
        history_path, history_rev = svn.fs.history_location(history, self.pool);
        if rev != history_rev:
            rev = history_rev

        author = svn.fs.revision_prop(self.fs_ptr, rev,
                                      svn.core.SVN_PROP_REVISION_AUTHOR, self.pool)
        msg = svn.fs.revision_prop(self.fs_ptr, rev,
                                   svn.core.SVN_PROP_REVISION_LOG, self.pool)
        msg_html = wiki_to_html(msg, self.req.hdf, self.env)
        date = svn.fs.revision_prop(self.fs_ptr, rev,
                                    svn.core.SVN_PROP_REVISION_DATE, self.pool)
        sdate = util.svn_date_to_string(date, self.pool)


        self.req.hdf.setValue('file.chgset_href', self.env.href.changeset(rev))
        self.req.hdf.setValue('file.rev', str(rev))
        self.req.hdf.setValue('file.rev_author', str(author))
        self.req.hdf.setValue('file.rev_date', sdate)
        self.req.hdf.setValue('file.rev_msg', msg_html)
        self.req.hdf.setValue('file.path', self.path)
        self.req.hdf.setValue('file.rawurl', self.env.href.file(self.path, rev,
                                                                'raw'))
        self.req.hdf.setValue('file.texturl', self.env.href.file(self.path, rev,
                                                                 'text'))
        self.req.hdf.setValue('file.logurl', self.env.href.log(self.path))

                
        # Try to do an educated guess about the mime-type
        self.mime_type = svn.fs.node_prop (root, self.path,
                                           svn.util.SVN_PROP_MIME_TYPE,
                                           self.pool)
        if not self.mime_type:
            self.mime_type = self.env.mimeview.get_mimetype(filename=self.path) or 'text/plain'
#            self.mime_type = mimetypes.guess_type(self.path)[0] or 'text/plain'
        elif self.mime_type == 'application/octet-stream':
            self.mime_type = self.env.mimeview.get_mimetype(filename=self.path) or \
                             'application/octet-stream'
            
        self.length = svn.fs.file_length(root, self.path, self.pool)
        date = svn.fs.revision_prop(self.fs_ptr, rev,
                                svn.util.SVN_PROP_REVISION_DATE, self.pool)
        date_seconds = svn.util.svn_time_from_cstring(date, self.pool) / 1000000
        self.last_modified = time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                      time.gmtime(date_seconds))
        fd = svn.fs.file_contents(root, self.path, self.pool)
        self.read_func = lambda x, f=fd: svn.util.svn_stream_read(f, x)
        
