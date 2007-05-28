# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Christopher Lenz <cmlenz@gmx.de>

from datetime import datetime
import os
import re
import shutil
import time
import unicodedata

from genshi.builder import tag

from trac import perm, util
from trac.config import BoolOption, IntOption
from trac.context import IContextProvider, Context, ResourceSystem
from trac.context import Context
from trac.core import *
from trac.env import IEnvironmentSetupParticipant
from trac.mimeview import *
from trac.timeline.api import TimelineEvent
from trac.util import get_reporter_id, create_unique_file, content_disposition
from trac.util.datefmt import utc
from trac.util.text import unicode_quote, unicode_unquote, pretty_size
from trac.web import HTTPBadRequest, IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki.api import IWikiSyntaxProvider


class InvalidAttachment(TracError):
    """Exception raised when attachment validation fails."""


class IAttachmentChangeListener(Interface):
    """Extension point interface for components that require notification when
    attachments are created or deleted."""

    def attachment_added(attachment):
        """Called when an attachment is added."""

    def attachment_deleted(attachment):
        """Called when an attachment is deleted."""


class IAttachmentManipulator(Interface):
    """Extension point interface for components that need to manipulate
    attachments.
    
    Unlike change listeners, a manipulator can reject changes being committed
    to the database."""

    def prepare_attachment(req, attachment, fields):
        """Not currently called, but should be provided for future
        compatibility."""

    def validate_attachment(req, attachment):
        """Validate an attachment after upload but before being stored in Trac
        environment.
        
        Must return a list of `(field, message)` tuples, one for each problem
        detected. `field` can be any of `description`, `username`, `filename`,
        `content`, or `None` to indicate an overall problem with the
        attachment. Therefore, a return value of `[]` means everything is
        OK."""


class AttachmentContext(Context):
    """Context for attachment resources."""

    realm = 'attachment'

    # methods reimplemented from Context

    def get_resource(self):
        return Attachment(self.env, self.parent.realm, self.parent.id,
                          filename=self.id, db=self._db)

    def resource_href(self, path=None, **kwargs):
        """Return an URL to the attachment itself.

        A `format` keyword argument equal to `'raw'` will be converted
        to the raw-attachment prefix.
        """
        format = kwargs.get('format')
        prefix = 'attachment'
        if format == 'raw':
            kwargs.pop('format')
            prefix = 'raw-attachment'
        path = [unicode(p) for p in [prefix, self.parent.realm, self.parent.id,
                                     self.id, path] if p]
        return Context.resource_href(self, '/' + '/'.join(path), **kwargs)

    def permid(self):
        return self.parent.permid() + (self.realm, self.id)

    def name(self):
        if self.id:
            return "Attachment '%s' in %s" % (self.id, self.parent.name())
        else:
            return 'Attachments of ' + self.parent.name()

    def shortname(self):
        return '%s:%s' % (self.parent.shortname(), self.filename)

    def summary(self):
        return self.resource.description


class Attachment(object):

    def __init__(self, env, parent_realm, parent_id, filename=None, db=None):
        self.env = env
        self.parent_realm = parent_realm
        self.parent_id = unicode(parent_id)
        if filename:
            self._fetch(filename, db)
        else:
            self.filename = None
            self.description = None
            self.size = None
            self.date = None
            self.author = None
            self.ipnr = None

    def _fetch(self, filename, db=None):
        if not db:
            db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT filename,description,size,time,author,ipnr "
                       "FROM attachment WHERE type=%s AND id=%s "
                       "AND filename=%s ORDER BY time",
                       (self.parent_realm, unicode(self.parent_id), filename))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            self.filename = filename
            raise TracError('Attachment %s does not exist.' % (self.title),
                            'Invalid Attachment')
        self.filename = row[0]
        self.description = row[1]
        self.size = row[2] and int(row[2]) or 0
        time = row[3] and int(row[3]) or 0
        self.date = datetime.fromtimestamp(time, utc)
        self.author = row[4]
        self.ipnr = row[5]

    def _get_path(self):
        path = os.path.join(self.env.path, 'attachments', self.parent_realm,
                            unicode_quote(self.parent_id))
        if self.filename:
            path = os.path.join(path, unicode_quote(self.filename))
        return os.path.normpath(path)
    path = property(_get_path)

    def _get_title(self):
        return '%s:%s: %s' % (self.parent_realm, 
                              self.parent_id, self.filename)
    title = property(_get_title)

    def delete(self, db=None):
        assert self.filename, 'Cannot delete non-existent attachment'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        cursor.execute("DELETE FROM attachment WHERE type=%s AND id=%s "
                       "AND filename=%s", (self.parent_realm, self.parent_id,
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

        for listener in AttachmentModule(self.env).change_listeners:
            listener.attachment_deleted(self)


    def insert(self, filename, fileobj, size, t=None, db=None):
        # FIXME: `t` should probably be switched to `datetime` too
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        self.size = size and int(size) or 0
        timestamp = int(t or time.time())
        self.date = datetime.fromtimestamp(timestamp, utc)

        # Make sure the path to the attachment is inside the environment
        # attachments directory
        attachments_dir = os.path.join(os.path.normpath(self.env.path),
                                       'attachments')
        commonprefix = os.path.commonprefix([attachments_dir, self.path])
        assert commonprefix == attachments_dir

        if not os.access(self.path, os.F_OK):
            os.makedirs(self.path)
        filename = unicode_quote(filename)
        path, targetfile = create_unique_file(os.path.join(self.path,
                                                           filename))
        try:
            # Note: `path` is an unicode string because `self.path` was one.
            # As it contains only quoted chars and numbers, we can use `ascii`
            basename = os.path.basename(path).encode('ascii')
            filename = unicode_unquote(basename)

            cursor = db.cursor()
            cursor.execute("INSERT INTO attachment "
                           "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                           (self.parent_realm, self.parent_id, filename,
                            self.size, timestamp, self.description,
                            self.author, self.ipnr))
            shutil.copyfileobj(fileobj, targetfile)
            self.filename = filename

            self.env.log.info('New attachment: %s by %s', self.title,
                              self.author)

            if handle_ta:
                db.commit()

            for listener in AttachmentModule(self.env).change_listeners:
                listener.attachment_added(self)

        finally:
            targetfile.close()

    def select(cls, env, parent_realm, parent_id, db=None):
        if not db:
            db = env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT filename,description,size,time,author,ipnr "
                       "FROM attachment WHERE type=%s AND id=%s ORDER BY time",
                       (parent_realm, unicode(parent_id)))
        for filename,description,size,time,author,ipnr in cursor:
            attachment = Attachment(env, parent_realm, parent_id)
            attachment.filename = filename
            attachment.description = description
            attachment.size = size and int(size) or 0
            time = time and int(time) or 0
            attachment.date = datetime.fromtimestamp(time, utc)
            attachment.author = author
            attachment.ipnr = ipnr
            yield attachment

    def delete_all(cls, env, parent_realm, parent_id, db):
        """Delete all attachments of a given resource.

        As this is usually done while deleting the parent resource,
        the `db` argument is ''not'' optional here.
        """
        attachment_dir = None
        for attachment in list(cls.select(env, parent_realm, parent_id, db)):
            attachment_dir = os.path.dirname(attachment.path)
            attachment.delete(db)
        if attachment_dir:
            try:
                os.rmdir(attachment_dir)
            except OSError:
                env.log.error("Can't delete attachment directory %s",
                              attachment_dir, exc_info=True)
            
    select = classmethod(select)
    delete_all = classmethod(delete_all)

    def open(self):
        self.env.log.debug('Trying to open attachment at %s', self.path)
        try:
            fd = open(self.path, 'rb')
        except IOError:
            raise TracError('Attachment %s not found' % self.filename)
        return fd


class AttachmentModule(Component):

    implements(IEnvironmentSetupParticipant, IRequestHandler,
               INavigationContributor, IWikiSyntaxProvider,
               IContextProvider)

    change_listeners = ExtensionPoint(IAttachmentChangeListener)
    manipulators = ExtensionPoint(IAttachmentManipulator)

    CHUNK_SIZE = 4096

    max_size = IntOption('attachment', 'max_size', 262144,
        """Maximum allowed file size for ticket and wiki attachments.""")

    render_unsafe_content = BoolOption('attachment', 'render_unsafe_content',
                                       'false',
        """Whether attachments should be rendered in the browser, or
        only made downloadable.

        Pretty much any file may be interpreted as HTML by the browser,
        which allows a malicious user to attach a file containing cross-site
        scripting attacks.

        For public sites where anonymous users can create attachments it is
        recommended to leave this option disabled (which is the default).""")

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
        return req.args.get('realm')

    def get_navigation_items(self, req):
        return []

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'^/(raw-)?attachment/([^/]+)(?:[/:](.*))?$',
                         req.path_info)
        if match:
            raw, realm, filename = match.groups()
            if raw:
                req.args['format'] = 'raw'
            req.args['realm'] = realm
            if filename:
                req.args['path'] = filename.replace(':', '/')
            return True

    def process_request(self, req):
        parent_realm = req.args.get('realm')
        path = req.args.get('path')
        
        if not parent_realm or not path:
            raise HTTPBadRequest('Bad request')

        context = Context(self.env, req)

        action = req.args.get('action', 'view')
        if action == 'new':
            attachment = Attachment(self.env, parent_realm, path)
        else:
            segments = path.split('/')
            parent_id = '/'.join(segments[:-1])
            filename = len(segments) > 1 and segments[-1]
            if not filename: # if there's a trailing '/', show the list
                return self._render_list(context(parent_realm, parent_id) \
                                         ('attachment'))
            attachment = Attachment(self.env, parent_realm, parent_id,
                                    filename)

        ctx = context(attachment.parent_realm, attachment.parent_id) \
              ('attachment', attachment.filename, resource=attachment)
        add_link(req, 'up', ctx.parent.resource_href(), ctx.parent.name())
        
        if req.method == 'POST':
            if action == 'new':
                self._do_save(ctx)
            elif action == 'delete':
                self._do_delete(ctx)
        elif action == 'delete':
            data = self._render_confirm_delete(ctx)
        elif action == 'new':
            data = self._render_form(ctx)
        else:
            data = self._render_view(ctx)

        data['context'] = ctx

        add_stylesheet(req, 'common/css/code.css')
        return 'attachment.html', data, None

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        yield ('raw-attachment', self._format_link)
        yield ('attachment', self._format_link)

    # Public methods

    def get_history(self, start, stop, realm):
        """Return an iterable of tuples describing changes to attachments on
        a particular object realm.

        The tuples are in the form (change, realm, id, filename, time,
        description, author). `change` can currently only be `created`."""
        # Traverse attachment directory
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT type, id, filename, time, description, author "
                       "  FROM attachment "
                       "  WHERE time > %s AND time < %s "
                       "        AND type = %s", (start, stop, realm))
        for realm, id, filename, ts, description, author in cursor:
            time = datetime.fromtimestamp(ts, utc)
            yield ('created', realm, id, filename, time, description, author)

    def get_timeline_events(self, context, start, stop):
        """Return an iterable of events suitable for ITimelineEventProvider.

        `context` specifies the realm.
        """
        req = context.req
        perm_map = {'ticket': 'TICKET_VIEW', 'wiki': 'WIKI_VIEW'}
        for change, realm, id, filename, time, descr, author in \
                self.get_history(start, stop, context.realm):
            ctx = context(realm=realm, id=id)('attachment', filename)
            if perm_map[realm] not in req.perm(ctx):
                continue
            title = tag(tag.em(os.path.basename(filename)), ' attached to ',
                        tag.em(ctx.parent.name(), title=ctx.parent.summary()))
            event = TimelineEvent(self, 'attachment')
            event.set_changeinfo(time, author)
            event.add_markup(title=title)
            event.add_wiki(ctx, body=descr)
            yield event

    def event_formatter(self, event, key):
        return None
    
    # IContextProvider methods

    def get_context_classes(self):
        yield AttachmentContext

    # Internal methods

    def _do_save(self, context):
        req, attachment = context.req, context.resource
        perm_map = {'ticket': 'TICKET_APPEND', 'wiki': 'WIKI_MODIFY'}
        req.perm.require(perm_map[attachment.parent_realm], context)

        if 'cancel' in req.args:
            req.redirect(context.parent.resource_href())

        upload = req.args['attachment']
        if not hasattr(upload, 'filename') or not upload.filename:
            raise TracError('No file uploaded')
        if hasattr(upload.file, 'fileno'):
            size = os.fstat(upload.file.fileno())[6]
        else:
            upload.file.seek(0, 2) # seek to end of file
            size = upload.file.tell()
            upload.file.seek(0)
        if size == 0:
            raise TracError("Can't upload empty file")

        # Maximum attachment size (in bytes)
        max_size = self.max_size
        if max_size >= 0 and size > max_size:
            raise TracError('Maximum attachment size: %d bytes' % max_size,
                            'Upload failed')

        # We try to normalize the filename to unicode NFC if we can.
        # Files uploaded from OS X might be in NFD.
        filename = unicodedata.normalize('NFC', unicode(upload.filename,
                                                        'utf-8'))
        filename = filename.replace('\\', '/').replace(':', '/')
        filename = os.path.basename(filename)
        if not filename:
            raise TracError('No file uploaded')
        # Now the filename is known, update the attachment context
        context.id = filename

        attachment.description = req.args.get('description', '')
        attachment.author = get_reporter_id(req, 'author')
        attachment.ipnr = req.remote_addr

        # Validate attachment
        for manipulator in self.manipulators:
            for field, message in manipulator.validate_attachment(req,
                                                                  attachment):
                if field:
                    raise InvalidAttachment('Attachment field %s is invalid: %s'
                                            % (field, message))
                else:
                    raise InvalidAttachment('Invalid attachment: %s' % message)

        if req.args.get('replace'):
            try:
                old_attachment = Attachment(self.env, attachment.parent_realm,
                                            attachment.parent_id, filename)
                if not (old_attachment.author and req.authname \
                        and old_attachment.author == req.authname):
                    perm_map = {'ticket': 'TICKET_ADMIN', 'wiki': 'WIKI_DELETE'}
                    req.perm.require(perm_map[old_attachment.parent_realm], context)
                old_attachment.delete()
            except TracError:
                pass # don't worry if there's nothing to replace
            attachment.filename = None
        attachment.insert(filename, upload.file, size)

        # Redirect the user to list of attachments (must add a trailing '/')
        req.redirect(context.resource_href('..') + '/')

    def _do_delete(self, context):
        req, attachment = context.req, context.resource
        perm_map = {'ticket': 'TICKET_ADMIN', 'wiki': 'WIKI_DELETE'}
        req.perm.require(perm_map[attachment.parent_realm], context)

        parent_href = context.parent.resource_href()
        if 'cancel' in req.args:
            req.redirect(parent_href)

        context.resource.delete()

        # Redirect the user to the attachment parent page
        req.redirect(parent_href)

    def _render_confirm_delete(self, context):
        req, attachment = context.req, context.resource
        perm_map = {'ticket': 'TICKET_ADMIN', 'wiki': 'WIKI_DELETE'}
        req.perm.require(perm_map[attachment.parent_realm], context)

        attachment = context.resource
        return {'mode': 'delete', 'title': '%s (delete)' % context.name(),
                'attachment': attachment}

    def _render_form(self, context):
        req, attachment = context.req, context.resource
        perm_map = {'ticket': 'TICKET_APPEND', 'wiki': 'WIKI_MODIFY'}
        req.perm.require(perm_map[attachment.parent_realm], context)

        return {'mode': 'new', 'author': get_reporter_id(context.req)}

    def _render_list(self, context):
        req, attachment = context.req, context.resource
        perm_map = {'ticket': 'TICKET_VIEW', 'wiki': 'WIKI_VIEW'}
        req.perm.require(perm_map[attachment.parent_realm], context)

        data = {
            'mode': 'list', 'context': context,
            'attachments': Attachment.select(self.env, context.parent.realm,
                                             context.parent.id),
            }

        add_link(req, 'up', context.parent.resource_href(),
                 context.parent.name())
        
        return 'attachment.html', data, None

    def _render_view(self, context):
        req, attachment = context.req, context.resource
        perm_map = {'ticket': 'TICKET_VIEW', 'wiki': 'WIKI_VIEW'}
        req.perm.require(perm_map[attachment.parent_realm], context)

        req.check_modified(attachment.date)

        data = {'mode': 'view', 'title': context.name(),
                'attachment': attachment}

        perm_map = {'ticket': 'TICKET_ADMIN', 'wiki': 'WIKI_DELETE'}
        if perm_map[attachment.parent_realm] in req.perm(context):
            data['can_delete'] = True

        fd = attachment.open()
        try:
            mimeview = Mimeview(self.env)

            # MIME type detection
            str_data = fd.read(1000)
            fd.seek(0)
            
            mime_type = mimeview.get_mimetype(attachment.filename, str_data)

            # Eventually send the file directly
            format = req.args.get('format')
            if format in ('raw', 'txt'):
                if not self.render_unsafe_content:
                    # Force browser to download files instead of rendering
                    # them, since they might contain malicious code enabling 
                    # XSS attacks
                    req.send_header('Content-Disposition', 'attachment')
                if format == 'txt':
                      mime_type = 'text/plain'
                elif not mime_type:
                    mime_type = 'application/octet-stream'
                if 'charset=' not in mime_type:
                    charset = mimeview.get_charset(str_data, mime_type)
                    mime_type = mime_type + '; charset=' + charset
                req.send_file(attachment.path, mime_type)

            # add ''Plain Text'' alternate link if needed
            if (self.render_unsafe_content and 
                mime_type and not mime_type.startswith('text/plain')):
                plaintext_href = context.resource_href(format='txt')
                add_link(req, 'alternate', plaintext_href, 'Plain Text',
                         mime_type)

            # add ''Original Format'' alternate link (always)
            raw_href = context.resource_href(format='raw')
            add_link(req, 'alternate', raw_href, 'Original Format', mime_type)

            self.log.debug("Rendering preview of file %s with mime-type %s"
                           % (attachment.filename, mime_type))

            data['preview'] = mimeview.preview_data(
                context, fd, os.fstat(fd.fileno()).st_size, mime_type,
                attachment.filename, raw_href, annotations=['lineno'])
            return data
        finally:
            fd.close()

    def _format_link(self, formatter, ns, target, label):
        link, params, fragment = formatter.split_link(target)
        ids = link.split(':', 2)
        context = None
        if len(ids) == 3:
            known_realms = ResourceSystem(self.env).get_known_realms()
            # new-style attachment: TracLinks (filename:realm:id)
            if ids[1] in known_realms:
                context = formatter.context(ids[1], ids[2]) \
                          ('attachment', ids[0])
            else: # try old-style attachment: TracLinks (realm:id:filename)
                if ids[0] in known_realms:
                    context = formatter.context(ids[0], ids[1]) \
                              ('attachment', ids[2])
        else: # local attachment: TracLinks (filename)
            context = formatter.context('attachment', link)
        if context:
            try:
                attachment = context.resource
                format = None
                if ns.startswith('raw'):
                    format = 'raw'
                return tag.a(label, class_='attachment',
                             href=context.resource_href(format=format) + params,
                             title=context.name())
            except TracError, e:
                pass
        return tag.a(label, class_='missing attachment', rel='nofollow')
