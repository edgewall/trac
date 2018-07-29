# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2018 Edgewall Software
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
from tempfile import TemporaryFile
from zipfile import ZipFile, ZIP_DEFLATED
import errno
import hashlib
import os.path
import posixpath
import re
import shutil
import sys
import unicodedata

from genshi.builder import tag

from trac.admin import AdminCommandError, IAdminCommandProvider, PrefixList, \
                       console_datetime_format, get_dir_list
from trac.config import BoolOption, IntOption
from trac.core import *
from trac.mimeview import *
from trac.perm import PermissionError, IPermissionPolicy
from trac.resource import *
from trac.search import search_to_sql, shorten_result
from trac.util import content_disposition, create_zipinfo, get_reporter_id
from trac.util.datefmt import datetime_now, format_datetime, from_utimestamp, \
                              to_datetime, to_utimestamp, utc
from trac.util.text import exception_to_unicode, path_to_unicode, \
                           pretty_size, print_table, stripws, unicode_unquote
from trac.util.translation import _, tag_
from trac.web import HTTPBadRequest, IRequestHandler, RequestDone
from trac.web.chrome import (INavigationContributor, add_ctxtnav, add_link,
                             add_stylesheet, web_context, add_warning)
from trac.web.href import Href
from trac.wiki.api import IWikiSyntaxProvider
from trac.wiki.formatter import format_to


class InvalidAttachment(TracError):
    """Exception raised when attachment validation fails."""


class IAttachmentChangeListener(Interface):
    """Extension point interface for components that require
    notification when attachments are created or deleted."""

    def attachment_added(attachment):
        """Called when an attachment is added."""

    def attachment_deleted(attachment):
        """Called when an attachment is deleted."""

    def attachment_reparented(attachment, old_parent_realm, old_parent_id):
        """Called when an attachment is reparented."""


class IAttachmentManipulator(Interface):
    """Extension point interface for components that need to
    manipulate attachments.

    Unlike change listeners, a manipulator can reject changes being
    committed to the database."""

    def prepare_attachment(req, attachment, fields):
        """Not currently called, but should be provided for future
        compatibility."""

    def validate_attachment(req, attachment):
        """Validate an attachment after upload but before being stored
        in Trac environment.

        Must return a list of ``(field, message)`` tuples, one for
        each problem detected. ``field`` can be any of
        ``description``, ``username``, ``filename``, ``content``, or
        `None` to indicate an overall problem with the
        attachment. Therefore, a return value of ``[]`` means
        everything is OK."""


class ILegacyAttachmentPolicyDelegate(Interface):
    """Interface that can be used by plugins to seamlessly participate
       to the legacy way of checking for attachment permissions.

       This should no longer be necessary once it becomes easier to
       setup fine-grained permissions in the default permission store.
    """

    def check_attachment_permission(action, username, resource, perm):
        """Return the usual `True`/`False`/`None` security policy
           decision appropriate for the requested action on an
           attachment.

            :param action: one of ATTACHMENT_VIEW, ATTACHMENT_CREATE,
                                  ATTACHMENT_DELETE
            :param username: the user string
            :param resource: the `~trac.resource.Resource` for the
                             attachment. Note that when
                             ATTACHMENT_CREATE is checked, the
                             resource ``.id`` will be `None`.
            :param perm: the permission cache for that username and resource
            """


class AttachmentModule(Component):

    implements(IRequestHandler, INavigationContributor, IWikiSyntaxProvider,
               IResourceManager)

    realm = 'attachment'
    is_valid_default_handler = False

    change_listeners = ExtensionPoint(IAttachmentChangeListener)
    manipulators = ExtensionPoint(IAttachmentManipulator)

    CHUNK_SIZE = 4096

    max_size = IntOption('attachment', 'max_size', 262144,
        """Maximum allowed file size (in bytes) for attachments.""")

    max_zip_size = IntOption('attachment', 'max_zip_size', 2097152,
        """Maximum allowed total size (in bytes) for an attachment list to be
        downloadable as a `.zip`. Set this to -1 to disable download as `.zip`.
        (''since 1.0'')""")

    render_unsafe_content = BoolOption('attachment', 'render_unsafe_content',
                                       'false',
        """Whether attachments should be rendered in the browser, or
        only made downloadable.

        Pretty much any file may be interpreted as HTML by the browser,
        which allows a malicious user to attach a file containing cross-site
        scripting attacks.

        For public sites where anonymous users can create attachments it is
        recommended to leave this option disabled.""")

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return req.args.get('realm')

    def get_navigation_items(self, req):
        return []

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/(raw-|zip-)?attachment/([^/]+)(?:/(.*))?$',
                         req.path_info)
        if match:
            format, realm, path = match.groups()
            if format:
                req.args['format'] = format[:-1]
            req.args['realm'] = realm
            if path:
                req.args['path'] = path
            return True

    def process_request(self, req):
        parent_id = None
        parent_realm = req.args.get('realm')
        path = req.args.get('path')
        filename = None

        if not parent_realm or not path:
            raise HTTPBadRequest(_('Bad request'))
        if parent_realm == 'attachment':
            raise TracError(tag_("%(realm)s is not a valid parent realm",
                                 realm=tag.code(parent_realm)))

        parent_realm = Resource(parent_realm)
        action = req.args.get('action', 'view')
        if action == 'new':
            parent_id = path.rstrip('/')
        else:
            last_slash = path.rfind('/')
            if last_slash == -1:
                parent_id, filename = path, ''
            else:
                parent_id, filename = path[:last_slash], path[last_slash + 1:]

        parent = parent_realm(id=parent_id)
        if not resource_exists(self.env, parent):
            raise ResourceNotFound(
                _("Parent resource %(parent)s doesn't exist",
                  parent=get_resource_name(self.env, parent)))

        # Link the attachment page to parent resource
        parent_name = get_resource_name(self.env, parent)
        parent_url = get_resource_url(self.env, parent, req.href)
        add_link(req, 'up', parent_url, parent_name)
        add_ctxtnav(req, _('Back to %(parent)s', parent=parent_name),
                    parent_url)

        if not filename: # there's a trailing '/'
            if req.args.get('format') == 'zip':
                self._download_as_zip(req, parent)
            elif action != 'new':
                return self._render_list(req, parent)

        attachment = Attachment(self.env, parent.child(self.realm, filename))

        if req.method == 'POST':
            if action == 'new':
                data = self._do_save(req, attachment)
            elif action == 'delete':
                self._do_delete(req, attachment)
            else:
                raise HTTPBadRequest(_("Invalid request arguments."))
        elif action == 'delete':
            data = self._render_confirm_delete(req, attachment)
        elif action == 'new':
            data = self._render_form(req, attachment)
        else:
            data = self._render_view(req, attachment)

        add_stylesheet(req, 'common/css/code.css')
        return 'attachment.html', data, None

    # IWikiSyntaxProvider methods

    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        yield ('raw-attachment', self._format_link)
        yield ('attachment', self._format_link)

    # Public methods

    def viewable_attachments(self, context):
        """Return the list of viewable attachments in the given context.

        :param context: the `~trac.mimeview.api.RenderingContext`
                        corresponding to the parent
                        `~trac.resource.Resource` for the attachments
        """
        parent = context.resource
        attachments = []
        for attachment in Attachment.select(self.env, parent.realm, parent.id):
            if 'ATTACHMENT_VIEW' in context.perm(attachment.resource):
                attachments.append(attachment)
        return attachments

    def attachment_data(self, context):
        """Return a data dictionary describing the list of viewable
        attachments in the current context.
        """
        attachments = self.viewable_attachments(context)
        parent = context.resource
        total_size = sum(attachment.size for attachment in attachments)
        new_att = parent.child(self.realm)
        return {'attach_href': get_resource_url(self.env, new_att,
                                                context.href),
                'download_href': get_resource_url(self.env, new_att,
                                                  context.href, format='zip')
                                 if total_size <= self.max_zip_size else None,
                'can_create': 'ATTACHMENT_CREATE' in context.perm(new_att),
                'attachments': attachments,
                'parent': context.resource}

    def get_history(self, start, stop, realm):
        """Return an iterable of tuples describing changes to attachments on
        a particular object realm.

        The tuples are in the form (change, realm, id, filename, time,
        description, author). `change` can currently only be `created`.

        FIXME: no iterator
        """
        for realm, id, filename, ts, description, author in \
                self.env.db_query("""
                SELECT type, id, filename, time, description, author
                FROM attachment WHERE time > %s AND time < %s AND type = %s
                """, (to_utimestamp(start), to_utimestamp(stop), realm)):
            time = from_utimestamp(ts or 0)
            yield ('created', realm, id, filename, time, description, author)

    def get_timeline_events(self, req, resource_realm, start, stop):
        """Return an event generator suitable for ITimelineEventProvider.

        Events are changes to attachments on resources of the given
        `resource_realm.realm`.
        """
        for change, realm, id, filename, time, descr, author in \
                self.get_history(start, stop, resource_realm.realm):
            attachment = resource_realm(id=id).child(self.realm, filename)
            if 'ATTACHMENT_VIEW' in req.perm(attachment):
                yield ('attachment', time, author, (attachment, descr), self)

    def render_timeline_event(self, context, field, event):
        attachment, descr = event[3]
        if field == 'url':
            return self.get_resource_url(attachment, context.href)
        elif field == 'title':
            name = get_resource_name(self.env, attachment.parent)
            title = get_resource_summary(self.env, attachment.parent)
            return tag_("%(attachment)s attached to %(resource)s",
                        attachment=tag.em(os.path.basename(attachment.id)),
                        resource=tag.em(name, title=title))
        elif field == 'description':
            return format_to(self.env, None, context.child(attachment.parent),
                             descr)

    def get_search_results(self, req, resource_realm, terms):
        """Return a search result generator suitable for ISearchSource.

        Search results are attachments on resources of the given
        `resource_realm.realm` whose filename, description or author match
        the given terms.
        """
        with self.env.db_query as db:
            sql_query, args = search_to_sql(
                    db, ['filename', 'description', 'author'], terms)
            for id, time, filename, desc, author in db("""
                    SELECT id, time, filename, description, author
                    FROM attachment WHERE type = %s AND """ + sql_query,
                    (resource_realm.realm,) + args):
                attachment = resource_realm(id=id).child(self.realm, filename)
                if 'ATTACHMENT_VIEW' in req.perm(attachment):
                    yield (get_resource_url(self.env, attachment, req.href),
                           get_resource_shortname(self.env, attachment),
                           from_utimestamp(time), author,
                           shorten_result(desc, terms))

    # IResourceManager methods

    def get_resource_realms(self):
        yield self.realm

    def get_resource_url(self, resource, href, **kwargs):
        """Return an URL to the attachment itself.

        A `format` keyword argument equal to `'raw'` will be converted
        to the raw-attachment prefix.
        """
        if not resource.parent:
            return None
        format = kwargs.get('format')
        prefix = 'attachment'
        if format in ('raw', 'zip'):
            kwargs.pop('format')
            prefix = format + '-attachment'
        parent_href = unicode_unquote(get_resource_url(self.env,
                            resource.parent(version=None), Href('')))
        if not resource.id:
            # link to list of attachments, which must end with a trailing '/'
            # (see process_request)
            return href(prefix, parent_href, '', **kwargs)
        else:
            return href(prefix, parent_href, resource.id, **kwargs)

    def get_resource_description(self, resource, format=None, **kwargs):
        if not resource.parent:
            return _("Unparented attachment %(id)s", id=resource.id)
        if format == 'compact':
            return '%s (%s)' % (resource.id,
                    get_resource_name(self.env, resource.parent))
        elif format == 'summary':
            return Attachment(self.env, resource).description
        if resource.id:
            return _("Attachment '%(id)s' in %(parent)s", id=resource.id,
                     parent=get_resource_name(self.env, resource.parent))
        else:
            return _("Attachments of %(parent)s",
                     parent=get_resource_name(self.env, resource.parent))

    def resource_exists(self, resource):
        try:
            attachment = Attachment(self.env, resource)
            return os.path.exists(attachment.path)
        except ResourceNotFound:
            return False

    # Internal methods

    def _do_save(self, req, attachment):
        req.perm(attachment.resource).require('ATTACHMENT_CREATE')
        parent_resource = attachment.resource.parent

        if 'cancel' in req.args:
            req.redirect(get_resource_url(self.env, parent_resource, req.href))

        upload = req.args.getfirst('attachment')
        if not hasattr(upload, 'filename') or not upload.filename:
            raise TracError(_("No file uploaded"))
        if hasattr(upload.file, 'fileno'):
            size = os.fstat(upload.file.fileno())[6]
        else:
            upload.file.seek(0, 2) # seek to end of file
            size = upload.file.tell()
            upload.file.seek(0)
        if size == 0:
            raise TracError(_("Can't upload empty file"))

        # Maximum attachment size (in bytes)
        max_size = self.max_size
        if 0 <= max_size < size:
            raise TracError(_("Maximum attachment size: %(num)s",
                              num=pretty_size(max_size)), _("Upload failed"))

        filename = _normalized_filename(upload.filename)
        if not filename:
            raise TracError(_("No file uploaded"))
        # Now the filename is known, update the attachment resource
        attachment.filename = filename
        attachment.description = req.args.get('description', '')
        attachment.author = get_reporter_id(req, 'author')
        attachment.ipnr = req.remote_addr

        # Validate attachment
        valid = True
        for manipulator in self.manipulators:
            for field, message in manipulator.validate_attachment(req,
                                                                  attachment):
                valid = False
                if field:
                    add_warning(req,
                        tag_("Attachment field %(field)s is invalid: "
                             "%(message)s", field=tag.strong(field),
                             message=message))
                else:
                    add_warning(req,
                        tag_("Invalid attachment: %(message)s",
                             message=message))
        if not valid:
            # Display the attach form with pre-existing data
            # NOTE: Local file path not known, file field cannot be repopulated
            add_warning(req, _('Note: File must be selected again.'))
            data = self._render_form(req, attachment)
            data['is_replace'] = req.args.get('replace')
            return data

        if req.args.get('replace'):
            try:
                old_attachment = Attachment(self.env,
                                            attachment.resource(id=filename))
                if not (req.authname and req.authname != 'anonymous'
                        and old_attachment.author == req.authname) \
                   and 'ATTACHMENT_DELETE' \
                                        not in req.perm(attachment.resource):
                    raise PermissionError(msg=_("You don't have permission to "
                        "replace the attachment %(name)s. You can only "
                        "replace your own attachments. Replacing other's "
                        "attachments requires ATTACHMENT_DELETE permission.",
                        name=filename))
                if (not attachment.description.strip() and
                        old_attachment.description):
                    attachment.description = old_attachment.description
                old_attachment.delete()
            except TracError:
                pass # don't worry if there's nothing to replace
        attachment.insert(filename, upload.file, size)

        req.redirect(get_resource_url(self.env, attachment.resource(id=None),
                                      req.href))

    def _do_delete(self, req, attachment):
        req.perm(attachment.resource).require('ATTACHMENT_DELETE')

        parent_href = get_resource_url(self.env, attachment.resource.parent,
                                       req.href)
        if 'cancel' in req.args:
            req.redirect(parent_href)

        attachment.delete()
        req.redirect(parent_href)

    def _render_confirm_delete(self, req, attachment):
        req.perm(attachment.resource).require('ATTACHMENT_DELETE')
        return {'mode': 'delete',
                'title': _('%(attachment)s (delete)',
                           attachment=get_resource_name(self.env,
                                                        attachment.resource)),
                'attachment': attachment}

    def _render_form(self, req, attachment):
        req.perm(attachment.resource).require('ATTACHMENT_CREATE')
        return {'mode': 'new', 'author': get_reporter_id(req),
                'attachment': attachment, 'max_size': self.max_size}

    def _download_as_zip(self, req, parent, attachments=None):
        if attachments is None:
            attachments = self.viewable_attachments(web_context(req, parent))
        total_size = sum(attachment.size for attachment in attachments)
        if total_size > self.max_zip_size:
            raise TracError(_("Maximum total attachment size: %(num)s",
                              num=pretty_size(self.max_zip_size)), _("Download failed"))

        req.send_response(200)
        req.send_header('Content-Type', 'application/zip')
        filename = 'attachments-%s-%s.zip' % \
                   (parent.realm, re.sub(r'[/\\:]', '-', unicode(parent.id)))
        req.send_header('Content-Disposition',
                        content_disposition('inline', filename))
        req.end_headers()

        def write_partial(fileobj, start):
            end = fileobj.tell()
            fileobj.seek(start, 0)
            remaining = end - start
            while remaining > 0:
                chunk = fileobj.read(min(remaining, 4096))
                req.write(chunk)
                remaining -= len(chunk)
            fileobj.seek(end, 0)
            return end

        pos = 0
        fileobj = TemporaryFile(prefix='trac-', suffix='.zip')
        try:
            zipfile = ZipFile(fileobj, 'w', ZIP_DEFLATED)
            for attachment in attachments:
                zipinfo = create_zipinfo(attachment.filename,
                                         mtime=attachment.date,
                                         comment=attachment.description)
                try:
                    with attachment.open() as fd:
                        zipfile.writestr(zipinfo, fd.read())
                except ResourceNotFound:
                    pass  # skip missing files
                else:
                    pos = write_partial(fileobj, pos)
        finally:
            try:
                zipfile.close()
                write_partial(fileobj, pos)
            finally:
                fileobj.close()
        raise RequestDone

    def _render_list(self, req, parent):
        data = {
            'mode': 'list',
            'attachment': None, # no specific attachment
            'attachments': self.attachment_data(web_context(req, parent))
        }

        return 'attachment.html', data, None

    def _render_view(self, req, attachment):
        req.perm(attachment.resource).require('ATTACHMENT_VIEW')
        can_delete = 'ATTACHMENT_DELETE' in req.perm(attachment.resource)
        req.check_modified(attachment.date, str(can_delete))

        data = {'mode': 'view',
                'title': get_resource_name(self.env, attachment.resource),
                'attachment': attachment}

        with attachment.open() as fd:
            mimeview = Mimeview(self.env)

            # MIME type detection
            str_data = fd.read(1000)
            fd.seek(0)

            mime_type = mimeview.get_mimetype(attachment.filename, str_data)

            # Eventually send the file directly
            format = req.args.get('format')
            if format == 'zip':
                self._download_as_zip(req, attachment.resource.parent,
                                      [attachment])
            elif format in ('raw', 'txt'):
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
                plaintext_href = get_resource_url(self.env,
                                                  attachment.resource,
                                                  req.href, format='txt')
                add_link(req, 'alternate', plaintext_href, _('Plain Text'),
                         mime_type)

            # add ''Original Format'' alternate link (always)
            raw_href = get_resource_url(self.env, attachment.resource,
                                        req.href, format='raw')
            add_link(req, 'alternate', raw_href, _('Original Format'),
                     mime_type)

            self.log.debug("Rendering preview of file %s with mime-type %s",
                           attachment.filename, mime_type)

            data['preview'] = mimeview.preview_data(
                web_context(req, attachment.resource), fd,
                os.fstat(fd.fileno()).st_size, mime_type,
                attachment.filename, raw_href, annotations=['lineno'])
            return data

    def _format_link(self, formatter, ns, target, label):
        link, params, fragment = formatter.split_link(target)
        ids = link.split(':', 2)
        attachment = None
        if len(ids) == 3:
            known_realms = ResourceSystem(self.env).get_known_realms()
            # new-style attachment: TracLinks (filename:realm:id)
            if ids[1] in known_realms:
                attachment = Resource(ids[1], ids[2]).child(self.realm,
                                                            ids[0])
            else: # try old-style attachment: TracLinks (realm:id:filename)
                if ids[0] in known_realms:
                    attachment = Resource(ids[0], ids[1]).child(self.realm,
                                                                ids[2])
        else: # local attachment: TracLinks (filename)
            attachment = formatter.resource.child(self.realm, link)
        if attachment and 'ATTACHMENT_VIEW' in formatter.perm(attachment):
            try:
                model = Attachment(self.env, attachment)
                raw_href = get_resource_url(self.env, attachment,
                                            formatter.href, format='raw')
                if ns.startswith('raw'):
                    return tag.a(label, class_='attachment',
                                 href=raw_href + params,
                                 title=get_resource_name(self.env, attachment))
                href = get_resource_url(self.env, attachment, formatter.href)
                title = get_resource_name(self.env, attachment)
                return tag(tag.a(label, class_='attachment', title=title,
                                 href=href + params),
                           tag.a(u'\u200b', class_='trac-rawlink',
                                 href=raw_href + params, title=_("Download")))
            except ResourceNotFound:
                pass
            # FIXME: should be either:
            #
            # model = Attachment(self.env, attachment)
            # if model.exists:
            #     ...
            #
            # or directly:
            #
            # if attachment.exists:
            #
            # (related to #4130)
        return tag.a(label, class_='missing attachment')


class Attachment(object):
    """Represents an attachment (new or existing).

    :since 1.0.5: `ipnr` is deprecated and will be removed in 1.3.1
    """

    realm = AttachmentModule.realm

    @property
    def resource(self):
        return Resource(self.parent_realm, self.parent_id) \
               .child(self.realm, self.filename)

    def __init__(self, env, parent_realm_or_attachment_resource,
                 parent_id=None, filename=None):
        if isinstance(parent_realm_or_attachment_resource, Resource):
            resource = parent_realm_or_attachment_resource
            self.parent_realm = resource.parent.realm
            self.parent_id = unicode(resource.parent.id)
            self.filename = resource.id
        else:
            self.parent_realm = parent_realm_or_attachment_resource
            self.parent_id = unicode(parent_id)
            self.filename = filename

        self.env = env
        if self.filename:
            self._fetch(self.filename)
        else:
            self.filename = None
            self.description = None
            self.size = None
            self.date = None
            self.author = None
            self.ipnr = None

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, self.filename)

    def _from_database(self, filename, description, size, time, author, ipnr):
        self.filename = filename
        self.description = description
        self.size = int(size) if size else 0
        self.date = from_utimestamp(time or 0)
        self.author = author
        self.ipnr = ipnr

    def _fetch(self, filename):
        for row in self.env.db_query("""
                SELECT filename, description, size, time, author, ipnr
                FROM attachment WHERE type=%s AND id=%s AND filename=%s
                ORDER BY time
                """, (self.parent_realm, unicode(self.parent_id), filename)):
            self._from_database(*row)
            break
        else:
            self.filename = filename
            raise ResourceNotFound(_("Attachment '%(title)s' does not exist.",
                                     title=self.title),
                                   _('Invalid Attachment'))

    # _get_path() and _get_hashed_filename() are class methods so that they
    # can be used in db28.py.

    @classmethod
    def _get_path(cls, env_path, parent_realm, parent_id, filename):
        """Get the path of an attachment.

        WARNING: This method is used by db28.py for moving attachments from
        the old "attachments" directory to the "files" directory. Please check
        all changes so that they don't break the upgrade.
        """
        path = os.path.join(env_path, 'files', 'attachments',
                            parent_realm)
        hash = hashlib.sha1(parent_id.encode('utf-8')).hexdigest()
        path = os.path.join(path, hash[0:3], hash)
        if filename:
            path = os.path.join(path, cls._get_hashed_filename(filename))
        return os.path.normpath(path)

    _extension_re = re.compile(r'\.[A-Za-z0-9]+\Z')

    @classmethod
    def _get_hashed_filename(cls, filename):
        """Get the hashed filename corresponding to the given filename.

        WARNING: This method is used by db28.py for moving attachments from
        the old "attachments" directory to the "files" directory. Please check
        all changes so that they don't break the upgrade.
        """
        hash = hashlib.sha1(filename.encode('utf-8')).hexdigest()
        match = cls._extension_re.search(filename)
        return hash + match.group(0) if match else hash

    @property
    def path(self):
        return self._get_path(self.env.path, self.parent_realm, self.parent_id,
                              self.filename)

    @property
    def title(self):
        return '%s:%s: %s' % (self.parent_realm, self.parent_id, self.filename)

    def delete(self):
        """Delete the attachment, both the record in the database and
        the file itself.
        """
        assert self.filename, "Cannot delete non-existent attachment"

        with self.env.db_transaction as db:
            db("""
                DELETE FROM attachment WHERE type=%s AND id=%s AND filename=%s
                """, (self.parent_realm, self.parent_id, self.filename))
            path = self.path
            if os.path.isfile(path):
                try:
                    os.unlink(path)
                except OSError as e:
                    self.env.log.error("Failed to delete attachment "
                                       "file %s: %s",
                                       path,
                                       exception_to_unicode(e, traceback=True))
                    raise TracError(_("Could not delete attachment"))

        self.env.log.info("Attachment removed: %s", self.title)

        for listener in AttachmentModule(self.env).change_listeners:
            listener.attachment_deleted(self)

    def reparent(self, new_realm, new_id):
        assert self.filename, "Cannot reparent non-existent attachment"
        new_id = unicode(new_id)
        new_path = self._get_path(self.env.path, new_realm, new_id,
                                  self.filename)

        # Make sure the path to the attachment is inside the environment
        # attachments directory
        attachments_dir = os.path.join(os.path.normpath(self.env.path),
                                       'files', 'attachments')
        commonprefix = os.path.commonprefix([attachments_dir, new_path])
        if commonprefix != attachments_dir:
            raise TracError(_('Cannot reparent attachment "%(att)s" as '
                              '%(realm)s:%(id)s is invalid',
                              att=self.filename, realm=new_realm, id=new_id))

        if os.path.exists(new_path):
            raise TracError(_('Cannot reparent attachment "%(att)s" as '
                              'it already exists in %(realm)s:%(id)s',
                              att=self.filename, realm=new_realm, id=new_id))
        with self.env.db_transaction as db:
            db("""UPDATE attachment SET type=%s, id=%s
                  WHERE type=%s AND id=%s AND filename=%s
                  """, (new_realm, new_id, self.parent_realm, self.parent_id,
                        self.filename))
            dirname = os.path.dirname(new_path)
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            path = self.path
            if os.path.isfile(path):
                try:
                    os.rename(path, new_path)
                except OSError as e:
                    self.env.log.error("Failed to move attachment file %s: %s",
                                       path,
                                       exception_to_unicode(e, traceback=True))
                    raise TracError(_("Could not reparent attachment %(name)s",
                                      name=self.filename))

        old_realm, old_id = self.parent_realm, self.parent_id
        self.parent_realm, self.parent_id = new_realm, new_id

        self.env.log.info("Attachment reparented: %s", self.title)

        for listener in AttachmentModule(self.env).change_listeners:
            if hasattr(listener, 'attachment_reparented'):
                listener.attachment_reparented(self, old_realm, old_id)

    def insert(self, filename, fileobj, size, t=None):
        """Create a new Attachment record and save the file content.
        """
        self.size = int(size) if size else 0
        self.filename = None
        if t is None:
            t = datetime_now(utc)
        elif not isinstance(t, datetime): # Compatibility with 0.11
            t = to_datetime(t, utc)
        self.date = t

        parent_resource = Resource(self.parent_realm, self.parent_id)
        if not resource_exists(self.env, parent_resource):
            raise ResourceNotFound(
                _("%(parent)s doesn't exist, can't create attachment",
                  parent=get_resource_name(self.env, parent_resource)))

        # Make sure the path to the attachment is inside the environment
        # attachments directory
        attachments_dir = os.path.join(os.path.normpath(self.env.path),
                                       'files', 'attachments')
        dir = self.path
        commonprefix = os.path.commonprefix([attachments_dir, dir])
        if commonprefix != attachments_dir:
            raise TracError(_('Cannot create attachment "%(att)s" as '
                              '%(realm)s:%(id)s is invalid',
                              att=filename, realm=self.parent_realm,
                              id=self.parent_id))

        if not os.access(dir, os.F_OK):
            os.makedirs(dir)
        filename, targetfile = self._create_unique_file(dir, filename)
        with targetfile:
            with self.env.db_transaction as db:
                db("INSERT INTO attachment VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                   (self.parent_realm, self.parent_id, filename, self.size,
                    to_utimestamp(t), self.description, self.author,
                    self.ipnr))
                shutil.copyfileobj(fileobj, targetfile)
                self.filename = filename

                self.env.log.info("New attachment: %s by %s", self.title,
                                  self.author)

        for listener in AttachmentModule(self.env).change_listeners:
            listener.attachment_added(self)

    @classmethod
    def select(cls, env, parent_realm, parent_id):
        """Iterator yielding all `Attachment` instances attached to
        resource identified by `parent_realm` and `parent_id`.

        :return: a tuple containing the `filename`, `description`, `size`,
                 `time`, `author` and `ipnr`.
        :since 1.0.5: use of `ipnr` is deprecated and will be removed in 1.3.1
        """
        for row in env.db_query("""
                SELECT filename, description, size, time, author, ipnr
                FROM attachment WHERE type=%s AND id=%s ORDER BY time
                """, (parent_realm, unicode(parent_id))):
            attachment = Attachment(env, parent_realm, parent_id)
            attachment._from_database(*row)
            yield attachment

    @classmethod
    def delete_all(cls, env, parent_realm, parent_id):
        """Delete all attachments of a given resource.
        """
        attachment_dir = None
        with env.db_transaction as db:
            for attachment in cls.select(env, parent_realm, parent_id):
                attachment_dir = os.path.dirname(attachment.path)
                attachment.delete()
        if attachment_dir:
            try:
                os.rmdir(attachment_dir)
            except OSError as e:
                env.log.error("Can't delete attachment directory %s: %s",
                              attachment_dir,
                              exception_to_unicode(e, traceback=True))

    @classmethod
    def reparent_all(cls, env, parent_realm, parent_id, new_realm, new_id):
        """Reparent all attachments of a given resource to another resource."""
        attachment_dir = None
        with env.db_transaction as db:
            for attachment in list(cls.select(env, parent_realm, parent_id)):
                attachment_dir = os.path.dirname(attachment.path)
                attachment.reparent(new_realm, new_id)
        if attachment_dir:
            try:
                os.rmdir(attachment_dir)
            except OSError as e:
                env.log.error("Can't delete attachment directory %s: %s",
                              attachment_dir,
                              exception_to_unicode(e, traceback=True))

    def open(self):
        path = self.path
        self.env.log.debug('Trying to open attachment at %s', path)
        try:
            fd = open(path, 'rb')
        except IOError:
            raise ResourceNotFound(_("Attachment '%(filename)s' not found",
                                     filename=self.filename))
        return fd

    def _create_unique_file(self, dir, filename):
        parts = os.path.splitext(filename)
        flags = os.O_CREAT + os.O_WRONLY + os.O_EXCL
        if hasattr(os, 'O_BINARY'):
            flags += os.O_BINARY
        idx = 1
        while 1:
            path = os.path.join(dir, self._get_hashed_filename(filename))
            try:
                return filename, os.fdopen(os.open(path, flags, 0666), 'w')
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
                idx += 1
                # A sanity check
                if idx > 100:
                    raise Exception('Failed to create unique name: ' + path)
                filename = '%s.%d%s' % (parts[0], idx, parts[1])


class LegacyAttachmentPolicy(Component):

    implements(IPermissionPolicy)

    delegates = ExtensionPoint(ILegacyAttachmentPolicyDelegate)

    realm = AttachmentModule.realm

    # IPermissionPolicy methods

    _perm_maps = {
        'ATTACHMENT_CREATE': {'ticket': 'TICKET_APPEND', 'wiki': 'WIKI_MODIFY',
                              'milestone': 'MILESTONE_MODIFY'},
        'ATTACHMENT_VIEW': {'ticket': 'TICKET_VIEW', 'wiki': 'WIKI_VIEW',
                            'milestone': 'MILESTONE_VIEW'},
        'ATTACHMENT_DELETE': {'ticket': 'TICKET_ADMIN', 'wiki': 'WIKI_DELETE',
                              'milestone': 'MILESTONE_DELETE'},
    }

    def check_permission(self, action, username, resource, perm):
        perm_map = self._perm_maps.get(action)
        if not perm_map or not resource or resource.realm != self.realm:
            return
        legacy_action = perm_map.get(resource.parent.realm)
        if legacy_action:
            decision = legacy_action in perm(resource.parent)
            if not decision:
                self.log.debug('LegacyAttachmentPolicy denied %s access to '
                               '%s. User needs %s',
                               username, resource, legacy_action)
            return decision
        else:
            for d in self.delegates:
                decision = d.check_attachment_permission(action, username,
                                                         resource, perm)
                if decision is not None:
                    return decision


class AttachmentAdmin(Component):
    """trac-admin command provider for attachment administration."""

    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods

    def get_admin_commands(self):
        yield ('attachment list', '<realm:id>',
               """List attachments of a resource

               The resource is identified by its realm and identifier.""",
               self._complete_list, self._do_list)
        yield ('attachment add', '<realm:id> <path> [author] [description]',
               """Attach a file to a resource

               The resource is identified by its realm and identifier. The
               attachment will be named according to the base name of the file.
               """,
               self._complete_add, self._do_add)
        yield ('attachment remove', '<realm:id> <name>',
               """Remove an attachment from a resource

               The resource is identified by its realm and identifier.""",
               self._complete_remove, self._do_remove)
        yield ('attachment export', '<realm:id> <name> [destination]',
               """Export an attachment from a resource to a file or stdout

               The resource is identified by its realm and identifier. If no
               destination is specified, the attachment is output to stdout.
               """,
               self._complete_export, self._do_export)

    def get_realm_list(self):
        rs = ResourceSystem(self.env)
        return PrefixList([each + ":" for each in rs.get_known_realms()])

    def split_resource(self, resource):
        result = resource.split(':', 1)
        if len(result) != 2:
            raise AdminCommandError(_("Invalid resource identifier '%(id)s'",
                                      id=resource))
        return result

    def get_attachment_list(self, resource):
        (realm, id) = self.split_resource(resource)
        return [a.filename for a in Attachment.select(self.env, realm, id)]

    def _complete_list(self, args):
        if len(args) == 1:
            return self.get_realm_list()

    def _complete_add(self, args):
        if len(args) == 1:
            return self.get_realm_list()
        elif len(args) == 2:
            return get_dir_list(args[1])

    def _complete_remove(self, args):
        if len(args) == 1:
            return self.get_realm_list()
        elif len(args) == 2:
            return self.get_attachment_list(args[0])

    def _complete_export(self, args):
        if len(args) < 3:
            return self._complete_remove(args)
        elif len(args) == 3:
            return get_dir_list(args[2])

    def _do_list(self, resource):
        (realm, id) = self.split_resource(resource)
        print_table([(a.filename, pretty_size(a.size), a.author,
                      format_datetime(a.date, console_datetime_format),
                      a.description)
                     for a in Attachment.select(self.env, realm, id)],
                    [_('Name'), _('Size'), _('Author'), _('Date'),
                     _('Description')])

    def _do_add(self, resource, path, author='trac', description=''):
        (realm, id) = self.split_resource(resource)
        attachment = Attachment(self.env, realm, id)
        attachment.author = author
        attachment.description = description
        filename = _normalized_filename(os.path.basename(path))
        with open(path, 'rb') as f:
            attachment.insert(filename, f, os.path.getsize(path))

    def _do_remove(self, resource, name):
        (realm, id) = self.split_resource(resource)
        attachment = Attachment(self.env, realm, id, name)
        attachment.delete()

    def _do_export(self, resource, name, destination=None):
        (realm, id) = self.split_resource(resource)
        attachment = Attachment(self.env, realm, id, name)
        if destination is not None:
            if os.path.isdir(destination):
                destination = os.path.join(destination, name)
            if os.path.isfile(destination):
                raise AdminCommandError(_("File '%(name)s' exists",
                                          name=path_to_unicode(destination)))
        with attachment.open() as input:
            output = open(destination, "wb") if destination is not None \
                     else sys.stdout
            try:
                shutil.copyfileobj(input, output)
            finally:
                if destination is not None:
                    output.close()


_control_codes_re = re.compile(
    '[' +
    ''.join(filter(lambda c: unicodedata.category(c) == 'Cc',
                   map(unichr, xrange(0x10000)))) +
    ']')

def _normalized_filename(filepath):
    # We try to normalize the filename to unicode NFC if we can.
    # Files uploaded from OS X might be in NFD.
    if not isinstance(filepath, unicode):
        filepath = unicode(filepath, 'utf-8')
    filepath = unicodedata.normalize('NFC', filepath)
    # Replace control codes with spaces, e.g. NUL, LF, DEL, U+009F
    filepath = _control_codes_re.sub(' ', filepath)
    # Replace backslashes with slashes if filename is Windows full path
    if filepath.startswith('\\') or re.match(r'[A-Za-z]:\\', filepath):
        filepath = filepath.replace('\\', '/')
    # We want basename to be delimited by only slashes on all platforms
    filename = posixpath.basename(filepath)
    filename = stripws(filename)
    return filename
