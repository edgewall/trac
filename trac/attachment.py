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

import os
import urllib

from trac import perm, util
from trac.Module import Module
from trac.web.main import add_link


class AttachmentModule(Module):

    CHUNK_SIZE = 4096
    DISP_MAX_FILE_SIZE = 256 * 1024

    def get_parent_link(self, parent_type, parent_id):
        if parent_type == 'ticket':
            return ('Ticket #' + parent_id, self.env.href.ticket(parent_id))
        elif parent_type == 'wiki':
            return (parent_id, self.env.href.wiki(parent_id))
        else:
            return (None, None)

    def render(self, req):
        parent_type = req.args.get('type')
        path = req.args.get('path')
        if not parent_type or not path:
            raise util.TracError('Bad request')
        if not parent_type in ['ticket', 'wiki']:
            raise util.TracError('Unknown attachment type')

        action = req.args.get('action', 'view')
        if action == 'new':
            self.render_form(req, parent_type, path)
        elif action == 'save':
            self.save_attachment(req, parent_type, path)
        else:
            segments = path.split('/')
            parent_id = '/'.join(segments[:-1])
            filename = segments[-1]
            if action == 'delete':
                self.delete_attachment(req, parent_type, parent_id, filename)
            else:
                self.render_view(req, parent_type, parent_id, filename)

    def render_form(self, req, parent_type, parent_id):
        perm_map = {'ticket': perm.TICKET_APPEND, 'wiki': perm.WIKI_MODIFY}
        self.perm.assert_permission(perm_map[parent_type])

        text, link = self.get_parent_link(parent_type, parent_id)
        req.hdf['attachment'] = {
            'mode': 'new',
            'parent_type': parent_type,
            'parent_id': parent_id,
            'parent_name': text,
            'parent_href': link,
            'author': util.get_reporter_id(req)
        }

        req.display('attachment.cs')

    def save_attachment(self, req, parent_type, parent_id):
        perm_map = {'ticket': perm.TICKET_APPEND, 'wiki': perm.WIKI_MODIFY}
        self.perm.assert_permission(perm_map[parent_type])

        if req.args.has_key('cancel'):
            req.redirect(self.get_parent_link(parent_type, parent_id)[1])

        attachment = req.args['attachment']
        if not attachment.filename:
            raise util.TracError, 'No file uploaded'
        description = req.args.get('description')
        author = req.args.get('author')

        filename = self.env.create_attachment(self.db, parent_type, parent_id,
                                              attachment, description, author,
                                              req.remote_addr)

        # Redirect the user to the newly created attachment
        req.redirect(self.env.href.attachment(parent_type, parent_id,
                                              filename))

    def delete_attachment(self, req, parent_type, parent_id, filename):
        perm_map = {'ticket': perm.TICKET_ADMIN, 'wiki': perm.WIKI_DELETE}
        self.perm.assert_permission(perm_map[parent_type])

        self.env.delete_attachment(self.db, parent_type, parent_id, filename)
        text, link = self.get_parent_link(parent_type, parent_id)

        # Redirect the user to the attachment parent page
        req.redirect(link)

    def render_view(self, req, parent_type, parent_id, filename):
        perm_map = {'ticket': perm.TICKET_VIEW, 'wiki': perm.WIKI_VIEW}
        self.perm.assert_permission(perm_map[parent_type])

        filename = os.path.basename(filename)
        path = os.path.join(self.env.get_attachments_dir(), parent_type,
                            urllib.quote(parent_id), urllib.quote(filename))
        self.log.debug('Trying to open attachment at %s' % path)
        try:
            fd = open(path, 'rb')
        except IOError:
            # Older versions of Trac saved attachments with unquoted filenames,
            # so try that. See #1112.
            path = os.path.join(self.env.get_attachments_dir(), parent_type,
                                urllib.quote(parent_id), filename)
            try:
                fd = open(path, 'rb')
            except IOError:
                raise util.TracError('Attachment not found')
        stat = os.fstat(fd.fileno())
        last_modified = stat[8]
        req.check_modified(last_modified)
        length = stat[6]
        mime_type = self.env.mimeview.get_mimetype(filename) or \
                    'application/octet-stream'
        charset = self.config.get('trac', 'default_charset')

        if req.args.get('format') in ('raw', 'txt'):
            self.render_view_raw(req, fd, mime_type, charset, length,
                                 last_modified)
            return

        # Render HTML view
        text, link = self.get_parent_link(parent_type, parent_id)
        add_link(req, 'up', link, text)

        raw_href = self.env.href.attachment(parent_type, parent_id, filename,
                                            format='raw')
        add_link(req, 'alternate', raw_href, 'Original Format', mime_type)

        req.hdf['trac.active_module'] = parent_type # Kludge
        req.hdf['title'] = '%s%s: %s' % (parent_type == 'ticket' and '#' or '',
                                         parent_id, filename)
        req.hdf['attachment'] = {
            'parent_type': parent_type,
            'parent_id': parent_id,
            'parent_name': text,
            'parent_href': link,
            'filename': urllib.unquote(filename),
            'raw_href': raw_href
        }

        perm_map = {'ticket': perm.TICKET_ADMIN, 'wiki': perm.WIKI_DELETE}
        if self.perm.has_permission(perm_map[parent_type]):
            req.hdf['attachment.can_delete'] = 1

        self.log.debug("Rendering preview of file %s with mime-type %s"
                       % (filename, mime_type))
        data = fd.read(self.DISP_MAX_FILE_SIZE)
        if not self.env.mimeview.is_binary(data):
            data = util.to_utf8(data, charset)
            add_link(req, 'alternate',
                     self.env.href.attachment(parent_type, parent_id, filename,
                                              format='txt'),
                     'Plain Text', mime_type)
        if len(data) >= self.DISP_MAX_FILE_SIZE:
            req.hdf['attachment.max_file_size_reached'] = 1
            req.hdf['attachment.max_file_size'] = self.DISP_MAX_FILE_SIZE
            vdata = ''
        else:
            vdata = self.env.mimeview.display(data, filename=filename,
                                              mimetype=mime_type)
        req.hdf['attachment.preview'] = vdata

        req.display('attachment.cs')

    def render_view_raw(self, req, fd, mime_type, charset, length,
                        last_modified):
        data = fd.read(self.CHUNK_SIZE)
        if not self.env.mimeview.is_binary(data):
            if req.args.get('format') == 'txt':
                mime_type = 'text/plain'
            mime_type = mime_type + ';charset=' + charset

        req.send_response(200)
        req.send_header('Content-Type', mime_type)
        req.send_header('Content-Length', str(length))
        req.send_header('Last-Modified', util.http_date(last_modified))
        req.end_headers()

        while data:
            req.write(data)
            data = fd.read(self.CHUNK_SIZE)
