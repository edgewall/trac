# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Christopher Lenz <cmlenz@gmx.de>

from __future__ import generators
import os
import re
import shutil
import time
import urllib

from trac import perm, util
from trac.core import *
from trac.env import IEnvironmentSetupParticipant
from trac.mimeview import *
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.web.main import IRequestHandler


class Attachment(object):

    def __init__(self, env, parent_type, parent_id, filename=None, db=None):
        self.env = env
        self.parent_type = parent_type
        self.parent_id = str(parent_id)
        if filename:
            self._fetch(filename, db)
        else:
            self.filename = None
            self.description = None
            self.size = None
            self.time = None
            self.author = None
            self.ipnr = None

    def _fetch(self, filename, db=None):
        if not db:
            db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT filename,description,size,time,author,ipnr "
                       "FROM attachment WHERE type=%s AND id=%s "
                       "AND filename=%s ORDER BY time",
                       (self.parent_type, self.parent_id, filename))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            raise TracError('Attachment %s/%s/%s does not exist.'
                            % (self.parent_type, self.parent_id, filename),
                            'Invalid Attachment')
        self.filename = row[0]
        self.description = row[1]
        self.size = row[2] and int(row[2]) or 0
        self.time = row[3] and int(row[3]) or 0
        self.author = row[4]
        self.ipnr = row[5]

    def _get_path(self):
        path = os.path.join(self.env.path, 'attachments', self.parent_type,
                            urllib.quote(self.parent_id))
        if self.filename:
            path = os.path.join(path, urllib.quote(self.filename))
        return os.path.normpath(path)
    path = property(fget=lambda self: self._get_path())

    def delete(self, db=None):
        assert self.filename, 'Cannot delete non-existent attachment'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        cursor.execute("DELETE FROM attachment WHERE type=%s AND id=%s "
                       "AND filename=%s", (self.parent_type, self.parent_id,
                       self.filename))
        try:
            os.unlink(self.path)
        except OSError:
            raise TracError, 'Attachment not found'

        self.env.log.info('Attachment removed: %s/%s/%s'
                          % (self.parent_type, self.parent_id, self.filename))
        if handle_ta:
            db.commit()

    def insert(self, filename, fileobj, size, t=None, db=None):
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        # Maximum attachment size (in bytes)
        max_size = int(self.env.config.get('attachment', 'max_size'))
        if max_size >= 0 and size > max_size:
            raise TracError('Maximum attachment size: %d bytes' % max_size,
                            'Upload failed')
        self.size = size
        self.time = t or time.time()

        # Make sure the path to the attachment is inside the environment
        # attachments directory
        attachments_dir = os.path.join(self.env.path, 'attachments')
        commonprefix = os.path.commonprefix([attachments_dir, self.path])
        assert commonprefix == attachments_dir

        if not os.access(self.path, os.F_OK):
            os.makedirs(self.path)
        filename = urllib.quote(filename)
        try:
            path, targetfile = util.create_unique_file(os.path.join(self.path,
                                                                    filename))
            filename = urllib.unquote(os.path.basename(path))

            cursor = db.cursor()
            cursor.execute("INSERT INTO attachment "
                           "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                           (self.parent_type, self.parent_id, filename,
                            self.size, self.time, self.description, self.author,
                            self.ipnr))
            shutil.copyfileobj(fileobj, targetfile)
            self.filename = filename

            self.env.log.info('New attachment: %s/%s/%s by %s'
                              % (self.parent_type, self.parent_id,
                                 self.filename, self.author))
            if handle_ta:
                db.commit()
        finally:
            targetfile.close()

    def select(cls, env, parent_type, parent_id, db=None):
        if not db:
            db = env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT filename,description,size,time,author,ipnr "
                       "FROM attachment WHERE type=%s AND id=%s ORDER BY time",
                       (parent_type, parent_id))
        for filename,description,size,time,author,ipnr in cursor:
            attachment = Attachment(env, parent_type, parent_id)
            attachment.filename = filename
            attachment.description = description
            attachment.size = size
            attachment.time = time
            attachment.author = author
            attachment.ipnr = ipnr
            yield attachment

    select = classmethod(select)

    def open(self):
        self.env.log.debug('Trying to open attachment at %s' % self.path)
        try:
            fd = open(self.path, 'rb')
        except IOError:
            raise TracError('Attachment %s not found' % self.filename)
        return fd


def attachment_to_hdf(env, db, req, attachment):
    from trac.wiki import wiki_to_oneliner
    if not db:
        db = env.get_db_cnx()
    hdf = {
        'filename': attachment.filename,
        'description': wiki_to_oneliner(attachment.description, env, db),
        'author': util.escape(attachment.author),
        'ipnr': attachment.ipnr,
        'size': util.pretty_size(attachment.size),
        'time': time.strftime('%c', time.localtime(attachment.time)),
        'href': env.href.attachment(attachment.parent_type,
                                    attachment.parent_id,
                                    attachment.filename)
    }
    return hdf


class AttachmentModule(Component):

    implements(IEnvironmentSetupParticipant, IRequestHandler,
               INavigationContributor)

    CHUNK_SIZE = 4096
    DISP_MAX_FILE_SIZE = 256 * 1024

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        """Create the attachments directory."""
        if self.env.path:
            os.mkdir(os.path.join(self.env.path, 'attachments'))

    def environment_needs_upgrade(self, db):
        return False

    def upgrade_environment(self, db):
        pass

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return req.args.get('type')

    def get_navigation_items(self, req):
        return []

    # IReqestHandler methods

    def match_request(self, req):
        match = re.match(r'^/attachment/(ticket|wiki)(?:/(.*))?$', req.path_info)
        if match:
            req.args['type'] = match.group(1)
            req.args['path'] = match.group(2)
            return 1

    def process_request(self, req):
        parent_type = req.args.get('type')
        path = req.args.get('path')
        if not parent_type or not path:
            raise TracError('Bad request')
        if not parent_type in ['ticket', 'wiki']:
            raise TracError('Unknown attachment type')

        action = req.args.get('action', 'view')
        if action == 'new':
            attachment = Attachment(self.env, parent_type, path)
        else:
            segments = path.split('/')
            parent_id = '/'.join(segments[:-1])
            filename = segments[-1]
            attachment = Attachment(self.env, parent_type, parent_id, filename)

        if req.method == 'POST':
            if action == 'new':
                self._do_save(req, attachment)
            elif action == 'delete':
                self._do_delete(req, attachment)
        elif action == 'delete':
            self._render_confirm(req, attachment)
        elif action == 'new':
            self._render_form(req, attachment)
        else:
            self._render_view(req, attachment)

        add_stylesheet(req, 'code.css')
        return 'attachment.cs', None

    # Internal methods

    def _do_save(self, req, attachment):
        perm_map = {'ticket': perm.TICKET_APPEND, 'wiki': perm.WIKI_MODIFY}
        req.perm.assert_permission(perm_map[attachment.parent_type])

        if 'cancel' in req.args.keys():
            req.redirect(self.env.href(attachment.parent_type,
                                       attachment.parent_id))

        upload = req.args['attachment']
        if not upload.filename:
            raise TracError, 'No file uploaded'
        if hasattr(upload.file, 'fileno'):
            size = os.fstat(upload.file.fileno())[6]
        else:
            size = upload.file.len

        filename = upload.filename.replace('\\', '/').replace(':', '/')
        filename = os.path.basename(filename)
        assert filename, 'No file uploaded'

        # We try to normalize the filename to utf-8 NFC if we can.
        # Files uploaded from OS X might be in NFD.
        import sys, unicodedata
        if sys.version_info[0] > 2 or \
           (sys.version_info[0] == 2 and sys.version_info[1] >= 3):
           filename = unicodedata.normalize('NFC',
                                            unicode(filename,
                                                    'utf-8')).encode('utf-8')

        attachment.description = req.args.get('description', '')
        attachment.author = req.args.get('author', '')
        attachment.ipnr = req.remote_addr
        attachment.insert(filename, upload.file, size)

        # Redirect the user to the newly created attachment
        req.redirect(self.env.href.attachment(attachment.parent_type,
                                              attachment.parent_id,
                                              attachment.filename))

    def _do_delete(self, req, attachment):
        perm_map = {'ticket': perm.TICKET_ADMIN, 'wiki': perm.WIKI_DELETE}
        req.perm.assert_permission(perm_map[attachment.parent_type])

        if 'cancel' in req.args.keys():
            req.redirect(self.env.href.attachment(attachment.parent_type,
                                                  attachment.parent_id,
                                                  attachment.filename))

        attachment.delete()

        # Redirect the user to the attachment parent page
        req.redirect(self.env.href(attachment.parent_type,
                                   attachment.parent_id))

    def _get_parent_link(self, parent_type, parent_id):
        if parent_type == 'ticket':
            return ('Ticket #' + parent_id, self.env.href.ticket(parent_id))
        elif parent_type == 'wiki':
            return (parent_id, self.env.href.wiki(parent_id))
        return (None, None)

    def _render_confirm(self, req, attachment):
        perm_map = {'ticket': perm.TICKET_ADMIN, 'wiki': perm.WIKI_DELETE}
        req.perm.assert_permission(perm_map[attachment.parent_type])

        req.hdf['title'] = '%s%s: %s (delete)' \
                           % (attachment.parent_type == 'ticket' and '#' or '',
                              attachment.parent_id, attachment.filename)
        text, link = self._get_parent_link(attachment.parent_type,
                                           attachment.parent_id)
        req.hdf['attachment'] = {
            'filename': attachment.filename,
            'mode': 'delete',
            'parent': {'type': attachment.parent_type,
                       'id': attachment.parent_id, 'name': text, 'href': link}
        }

    def _render_form(self, req, attachment):
        perm_map = {'ticket': perm.TICKET_APPEND, 'wiki': perm.WIKI_MODIFY}
        req.perm.assert_permission(perm_map[attachment.parent_type])

        text, link = self._get_parent_link(attachment.parent_type,
                                           attachment.parent_id)
        req.hdf['attachment'] = {
            'mode': 'new',
            'author': util.get_reporter_id(req),
            'parent': {'type': attachment.parent_type,
                       'id': attachment.parent_id, 'name': text, 'href': link}
        }

    def _render_view(self, req, attachment):
        perm_map = {'ticket': perm.TICKET_VIEW, 'wiki': perm.WIKI_VIEW}
        req.perm.assert_permission(perm_map[attachment.parent_type])

        mimetype = get_mimetype(attachment.filename) or 'application/octet-stream'
        charset = self.config.get('trac', 'default_charset')

        if req.args.get('format') in ('raw', 'txt'):
            # Render raw file
            req.send_file(attachment.path, mimetype + ';charset=' + charset)
            return

        req.check_modified(attachment.time)

        # Render HTML view
        text, link = self._get_parent_link(attachment.parent_type,
                                           attachment.parent_id)
        add_link(req, 'up', link, text)

        req.hdf['title'] = '%s%s: %s' % (attachment.parent_type == 'ticket' and '#' or '',
                                         attachment.parent_id,
                                         attachment.filename)
        req.hdf['attachment'] = attachment_to_hdf(self.env, None, req, attachment)
        req.hdf['attachment.parent'] = {
            'type': attachment.parent_type, 'id': attachment.parent_id,
            'name': text, 'href': link,
        }

        raw_href = self.env.href.attachment(attachment.parent_type,
                                            attachment.parent_id,
                                            attachment.filename,
                                            format='raw')
        add_link(req, 'alternate', raw_href, 'Original Format', mimetype)
        req.hdf['attachment.raw_href'] = raw_href

        perm_map = {'ticket': perm.TICKET_ADMIN, 'wiki': perm.WIKI_DELETE}
        if req.perm.has_permission(perm_map[attachment.parent_type]):
            req.hdf['attachment.can_delete'] = 1

        self.log.debug("Rendering preview of file %s with mime-type %s"
                       % (attachment.filename, mimetype))
        fd = attachment.open()
        try:
            data = fd.read(self.DISP_MAX_FILE_SIZE)
            if not is_binary(data):
                data = util.to_utf8(data, charset)
                add_link(req, 'alternate',
                         self.env.href.attachment(attachment.parent_type,
                                                  attachment.parent_id,
                                                  attachment.filename,
                                                  format='txt'),
                         'Plain Text', mimetype)
            if len(data) >= self.DISP_MAX_FILE_SIZE:
                req.hdf['attachment.max_file_size_reached'] = 1
                req.hdf['attachment.max_file_size'] = self.DISP_MAX_FILE_SIZE
                vdata = ''
            else:
                mimeview = Mimeview(self.env)
                vdata = mimeview.render(req, mimetype, data,
                                        attachment.filename)
            req.hdf['attachment.preview'] = vdata
        finally:
            fd.close()
