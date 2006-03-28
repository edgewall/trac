# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

import os
import re
import shutil
import time
import unicodedata
import urllib

from trac import perm, util
from trac.config import *
from trac.core import *
from trac.env import IEnvironmentSetupParticipant
from trac.mimeview import *
from trac.util.markup import html
from trac.web import HTTPBadRequest, IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import IWikiSyntaxProvider


class Attachment(object):

    def __init__(self, env, parent_type, parent_id, filename=None, db=None):
        self.env = env
        self.parent_type = parent_type
        self.parent_id = unicode(parent_id)
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
                       (self.parent_type, unicode(self.parent_id), filename))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            self.filename = filename
            raise TracError('Attachment %s does not exist.' % (self.title),
                            'Invalid Attachment')
        self.filename = row[0]
        self.description = row[1]
        self.size = row[2] and int(row[2]) or 0
        self.time = row[3] and int(row[3]) or 0
        self.author = row[4]
        self.ipnr = row[5]

    def _get_path(self):
        path = os.path.join(self.env.path, 'attachments', self.parent_type,
                            util.unicode_quote(self.parent_id))
        if self.filename:
            path = os.path.join(path, util.unicode_quote(self.filename))
        return os.path.normpath(path)
    path = property(_get_path)

    def href(self, *args, **dict):
        return self.env.href.attachment(self.parent_type, self.parent_id,
                                        self.filename, *args, **dict)

    def _get_title(self):
        return '%s%s: %s' % (self.parent_type == 'ticket' and '#' or '',
                             self.parent_id, self.filename)
    title = property(_get_title)

    def _get_parent_href(self):
        return self.env.href(self.parent_type, self.parent_id)
    parent_href = property(_get_parent_href)

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
        if os.path.isfile(self.path):
            try:
                os.unlink(self.path)
            except OSError:
                self.env.log.error('Failed to delete attachment file %s',
                                   self.path, exc_info=True)
                if handle_ta:
                    db.rollback()
                raise TracError, 'Could not delete attachment'

        self.env.log.info('Attachment removed: %s' % self.title)
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
        attachments_dir = os.path.join(os.path.normpath(self.env.path),
                                       'attachments')
        commonprefix = os.path.commonprefix([attachments_dir, self.path])
        assert commonprefix == attachments_dir

        if not os.access(self.path, os.F_OK):
            os.makedirs(self.path)
        filename = urllib.quote(filename)
        path, targetfile = util.create_unique_file(os.path.join(self.path,
                                                                filename))
        try:
            filename = urllib.unquote(os.path.basename(path))

            cursor = db.cursor()
            cursor.execute("INSERT INTO attachment "
                           "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                           (self.parent_type, self.parent_id, filename,
                            self.size, self.time, self.description, self.author,
                            self.ipnr))
            shutil.copyfileobj(fileobj, targetfile)
            self.filename = filename

            self.env.log.info('New attachment: %s by %s', self.title,
                              self.author)
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
                       (parent_type, unicode(parent_id)))
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
        self.env.log.debug('Trying to open attachment at %s', self.path)
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
        'author': attachment.author,
        'ipnr': attachment.ipnr,
        'size': util.pretty_size(attachment.size),
        'time': util.format_datetime(attachment.time),
        'href': attachment.href()
    }
    return hdf


class AttachmentModule(Component):

    implements(IConfigurable, IEnvironmentSetupParticipant, IRequestHandler,
               INavigationContributor, IWikiSyntaxProvider)

    CHUNK_SIZE = 4096

    # IConfigurable methods

    def get_config_sections(self):
        yield ConfigSection('attachment', [
            ConfigOption('max_size', '262144',
                         """Maximum allowed file size for ticket and wiki
                         attachments
                         """),
            ConfigOption('render_unsafe_content', 'false',
                         """Whether non-binary attachments should be rendered in
                         the browser, or only made downloadable.

                         Pretty much any text file may be interpreted as HTML
                         by the browser, which allows a malicious user to
                         attach a file containing cross-site scripting attacks.

                         For public sites where anonymous users can create
                         attachments, it is recommended to leave this option off
                         (which is the default).
                         """)])

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
        match = re.match(r'^/attachment/(ticket|wiki)(?:[/:](.*))?$', req.path_info)
        if match:
            req.args['type'] = match.group(1)
            req.args['path'] = match.group(2).replace(':', '/')
            return 1

    def process_request(self, req):
        parent_type = req.args.get('type')
        path = req.args.get('path')
        if not parent_type or not path:
            raise HTTPBadRequest('Bad request')
        if not parent_type in ['ticket', 'wiki']:
            raise HTTPBadRequest('Unknown attachment type')

        action = req.args.get('action', 'view')
        if action == 'new':
            attachment = Attachment(self.env, parent_type, path)
        else:
            segments = path.split('/')
            parent_id = '/'.join(segments[:-1])
            filename = segments[-1]
            if len(segments) == 1 or not filename:
                raise HTTPBadRequest('Bad request')
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

        add_stylesheet(req, 'common/css/code.css')
        return 'attachment.cs', None

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        yield ('attachment', self._format_link)

    # Internal methods

    def _do_save(self, req, attachment):
        perm_map = {'ticket': 'TICKET_APPEND', 'wiki': 'WIKI_MODIFY'}
        req.perm.assert_permission(perm_map[attachment.parent_type])

        if req.args.has_key('cancel'):
            req.redirect(attachment.parent_href)

        upload = req.args['attachment']
        if not hasattr(upload, 'filename') or not upload.filename:
            raise TracError('No file uploaded')
        if hasattr(upload.file, 'fileno'):
            size = os.fstat(upload.file.fileno())[6]
        else:
            size = upload.file.len
        if size == 0:
            raise TracError('No file uploaded')

        filename = upload.filename.replace('\\', '/').replace(':', '/')
        filename = os.path.basename(filename)
        if not filename:
            raise TracError('No file uploaded')

        # We try to normalize the filename to utf-8 NFC if we can.
        # Files uploaded from OS X might be in NFD.
        filename = unicodedata.normalize('NFC',
                                         unicode(filename, 'utf-8')).encode('utf-8')

        attachment.description = req.args.get('description', '')
        attachment.author = req.args.get('author', '')
        attachment.ipnr = req.remote_addr
        if req.args.get('replace'):
            try:
                old_attachment = Attachment(self.env, attachment.parent_type,
                                            attachment.parent_id, filename)
                if not (old_attachment.author and req.authname \
                        and old_attachment.author == req.authname):
                    perm_map = {'ticket': 'TICKET_ADMIN', 'wiki': 'WIKI_DELETE'}
                    req.perm.assert_permission(perm_map[old_attachment.parent_type])
                old_attachment.delete()
            except TracError:
                pass # don't worry if there's nothing to replace
            attachment.filename = None
        attachment.insert(filename, upload.file, size)

        # Redirect the user to the newly created attachment
        req.redirect(attachment.href())

    def _do_delete(self, req, attachment):
        perm_map = {'ticket': 'TICKET_ADMIN', 'wiki': 'WIKI_DELETE'}
        req.perm.assert_permission(perm_map[attachment.parent_type])

        if req.args.has_key('cancel'):
            req.redirect(attachment.href())

        attachment.delete()

        # Redirect the user to the attachment parent page
        req.redirect(attachment.parent_href)

    def _get_parent_link(self, attachment):
        if attachment.parent_type == 'ticket':
            return ('Ticket #' + attachment.parent_id, attachment.parent_href)
        elif attachment.parent_type == 'wiki':
            return (attachment.parent_id, attachment.parent_href)
        return (None, None)

    def _render_confirm(self, req, attachment):
        perm_map = {'ticket': 'TICKET_ADMIN', 'wiki': 'WIKI_DELETE'}
        req.perm.assert_permission(perm_map[attachment.parent_type])

        req.hdf['title'] = '%s (delete)' % attachment.title
        text, link = self._get_parent_link(attachment)
        req.hdf['attachment'] = {
            'filename': attachment.filename,
            'mode': 'delete',
            'parent': {'type': attachment.parent_type,
                       'id': attachment.parent_id, 'name': text, 'href': link}
        }

    def _render_form(self, req, attachment):
        perm_map = {'ticket': 'TICKET_APPEND', 'wiki': 'WIKI_MODIFY'}
        req.perm.assert_permission(perm_map[attachment.parent_type])

        text, link = self._get_parent_link(attachment)
        req.hdf['attachment'] = {
            'mode': 'new',
            'author': util.get_reporter_id(req),
            'parent': {'type': attachment.parent_type,
                       'id': attachment.parent_id, 'name': text, 'href': link}
        }

    def _render_view(self, req, attachment):
        perm_map = {'ticket': 'TICKET_VIEW', 'wiki': 'WIKI_VIEW'}
        req.perm.assert_permission(perm_map[attachment.parent_type])

        req.check_modified(attachment.time)

        # Render HTML view
        text, link = self._get_parent_link(attachment)
        add_link(req, 'up', link, text)

        req.hdf['title'] = attachment.title
        req.hdf['attachment'] = attachment_to_hdf(self.env, None, req,
                                                  attachment)
        req.hdf['attachment.parent'] = {
            'type': attachment.parent_type, 'id': attachment.parent_id,
            'name': text, 'href': link,
        }

        perm_map = {'ticket': 'TICKET_ADMIN', 'wiki': 'WIKI_DELETE'}
        if req.perm.has_permission(perm_map[attachment.parent_type]):
            req.hdf['attachment.can_delete'] = 1

        fd = attachment.open()
        try:
            mimeview = Mimeview(self.env)
            data = fd.read(mimeview.max_preview_size())

            mime_type = get_mimetype(attachment.filename, data) or \
                        'application/octet-stream'
            self.log.debug("Rendering preview of file %s with mime-type %s"
                           % (attachment.filename, mime_type))

            raw_href = attachment.href(format='raw')
            add_link(req, 'alternate', raw_href, 'Original Format', mime_type)
            req.hdf['attachment.raw_href'] = raw_href

            format = req.args.get('format')
            render_unsafe = self.config.getbool('attachment',
                                                'render_unsafe_content')
            binary = is_binary(data)

            if format in ('raw', 'txt'): # Send raw file
                if not render_unsafe and not binary:
                    # Force browser to download HTML/SVG/etc pages that may
                    # contain malicious code enabling XSS attacks
                    req.send_header('Content-Disposition', 'attachment;' +
                                    'filename=' + attachment.filename)
                charset = mimeview.get_charset(data, mime_type)
                if render_unsafe and not binary and format == 'txt':
                    mime_type = 'text/plain'
                req.send_file(attachment.path,
                              mime_type + ';charset=' + charset)

            if render_unsafe and not binary:
                plaintext_href = attachment.href(format='txt')
                add_link(req, 'alternate', plaintext_href, 'Plain Text',
                         mime_type)

            hdf = mimeview.preview_to_hdf(req, data, mime_type,
                                          attachment.filename, None,
                                          annotations=['lineno'])
            req.hdf['attachment'] = hdf
        finally:
            fd.close()

    def _format_link(self, formatter, ns, link, label):
        ids = link.split(':', 2)
        params = ''
        if len(ids) == 3:
            parent_type, parent_id, filename = ids
        else:
            # FIXME: the formatter should know which object the text being
            #        formatter belongs to
            parent_type, parent_id = 'wiki', 'WikiStart'
            if formatter.req:
                path_info = formatter.req.path_info.split('/', 2)
                if len(path_info) > 1:
                    parent_type = path_info[1]
                if len(path_info) > 2:
                    parent_id = path_info[2]
            filename = link
        idx = filename.find('?')
        if idx >= 0:
            filename, params = filename[:idx], filename[idx:]
        try:
            attachment = Attachment(self.env, parent_type, parent_id, filename)
            return html.A(class_='attachment', href=attachment.href() + params,
                          title='Attachment %s' % attachment.title)[label]
        except TracError:
            return html.A(class_='missing attachment', rel='nofollow',
                          href=formatter.href())[label]
