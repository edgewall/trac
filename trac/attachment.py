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

import os
import time
import urllib

from trac import perm, util
from trac.Module import Module
from trac.WikiFormatter import wiki_to_html


class AttachmentModule(Module):
    template_name = 'attachment.cs'

    CHUNK_SIZE = 4096
    DISP_MAX_FILE_SIZE = 256 * 1024

    filename = None
    mime_type = None
    last_modified = None
    length = None
    read_func = None

    def get_attachment_parent_link(self):
        if self.attachment_type == 'ticket':
            return ('Ticket #' + self.attachment_id,
                    self.env.href.ticket(int(self.attachment_id)))
        elif self.attachment_type == 'wiki':
            return (self.attachment_id,
                    self.env.href.wiki(self.attachment_id))
        assert 0

    def render(self, req):
        self.perm.assert_permission(perm.FILE_VIEW)

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

            self.add_link('alternate',
                          self.env.href.attachment(self.attachment_type,
                                                   self.attachment_id,
                                                   self.filename, 'raw'),
                'Original Format', self.mime_type)

            perm_map = {'ticket': perm.TICKET_ADMIN, 'wiki': perm.WIKI_DELETE}
            if self.perm.has_permission(perm_map[self.attachment_type]):
                req.hdf['attachment.delete_href'] = '?delete=yes'

            return

        if req.args.has_key('description') and \
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

    def display(self, req):
        text, link = self.get_attachment_parent_link()
        self.add_link('up', link, text)
        req.hdf['title'] = '%s%s: %s' % (
                           self.attachment_type == 'ticket' and '#' or '',
                           self.attachment_id, self.filename)
        req.hdf['file.attachment_parent'] = text
        req.hdf['file.attachment_parent_href'] = link

        if self.view_form:
            req.hdf['attachment.mode'] = 'new'
            req.hdf['attachment.type'] = self.attachment_type
            req.hdf['attachment.id'] = self.attachment_id
            req.hdf['attachment.author'] = util.get_reporter_id(req)

        else:
            self.log.debug("Displaying file: %s  mime-type: %s"
                           % (self.filename, self.mime_type))
            req.hdf['file.filename'] = urllib.unquote(self.filename)
            req.hdf['trac.active_module'] = self.attachment_type # Kludge

            # We don't have to guess if the charset is specified in the
            # svn:mime-type property
            ctpos = self.mime_type.find('charset=')
            if ctpos >= 0:
                charset = self.mime_type[ctpos + 8:]
            else:
                charset = self.env.get_config('trac', 'default_charset',
                                              'iso-8859-15')
            data = util.to_utf8(self.read_func(self.DISP_MAX_FILE_SIZE),
                                charset)

            if len(data) == self.DISP_MAX_FILE_SIZE:
                req.hdf['file.max_file_size_reached'] = 1
                req.hdf['file.max_file_size'] = self.DISP_MAX_FILE_SIZE
                vdata = ' '
            else:
                vdata = self.env.mimeview.display(data, filename=self.filename,
                                                  mimetype=self.mime_type)
            req.hdf['file.preview'] = vdata

        Module.display(self, req)

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
