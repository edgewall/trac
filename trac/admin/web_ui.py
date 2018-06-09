# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2014 Edgewall Software
# Copyright (C) 2005 Jonas Borgström <jonas@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import os
import pkg_resources
import re
import shutil
from functools import partial

from trac import log
from trac.admin.api import IAdminPanelProvider
from trac.core import *
from trac.loader import get_plugin_info
from trac.perm import IPermissionRequestor, PermissionExistsError, \
                      PermissionSystem
from trac.util.datefmt import all_timezones, pytz
from trac.util.html import tag
from trac.util.text import exception_to_unicode, unicode_from_base64, \
                           unicode_to_base64
from trac.util.translation import _, Locale, get_available_locales, \
                                  ngettext, tag_
from trac.web.api import HTTPNotFound, IRequestHandler, \
                         is_valid_default_handler
from trac.web.chrome import Chrome, INavigationContributor, \
                            ITemplateProvider, add_notice, add_stylesheet, \
                            add_warning
from trac.wiki.formatter import format_to_html


class AdminModule(Component):
    """Web administration interface provider and panel manager."""

    implements(INavigationContributor, IRequestHandler, ITemplateProvider)

    panel_providers = ExtensionPoint(IAdminPanelProvider)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'admin'

    def get_navigation_items(self, req):
        # The 'Admin' navigation item is only visible if at least one
        # admin panel is available
        panels, providers = self._get_panels(req)
        if panels:
            yield 'mainnav', 'admin', tag.a(_("Admin"), href=req.href.admin())

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match('/admin(?:/([^/]+)(?:/([^/]+)(?:/(.+))?)?)?$',
                         req.path_info)
        if match:
            req.args['cat_id'] = match.group(1)
            req.args['panel_id'] = match.group(2)
            req.args['path_info'] = match.group(3)
            return True

    def process_request(self, req):
        panels, providers = self._get_panels(req)
        if not panels:
            raise HTTPNotFound(_("No administration panels available"))

        def _panel_order(panel):
            items = panel[::2]
            return items[0] != 'general', items != ('general', 'basics'), items
        panels.sort(key=_panel_order)

        cat_id = req.args.get('cat_id') or panels[0][0]
        panel_id = req.args.get('panel_id')
        path_info = req.args.get('path_info')
        if not panel_id:
            try:
                panel_id = \
                    filter(lambda panel: panel[0] == cat_id, panels)[0][2]
            except IndexError:
                raise HTTPNotFound(_("Unknown administration panel"))

        provider = providers.get((cat_id, panel_id))
        if not provider:
            raise HTTPNotFound(_("Unknown administration panel"))

        resp = provider.render_admin_panel(req, cat_id, panel_id, path_info)
        template, data = resp[:2]

        data.update({
            'active_cat': cat_id, 'active_panel': panel_id,
            'panel_href': partial(req.href, 'admin', cat_id, panel_id),
            'panels': [{
                'category': {'id': panel[0], 'label': panel[1]},
                'panel': {'id': panel[2], 'label': panel[3]}
            } for panel in panels]
        })

        add_stylesheet(req, 'common/css/admin.css')
        return resp

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename('trac.admin', 'templates')]

    # Internal methods

    def _get_panels(self, req):
        """Return a list of available admin panels."""
        panels = []
        providers = {}

        for provider in self.panel_providers:
            p = list(provider.get_admin_panels(req) or [])
            for panel in p:
                providers[(panel[0], panel[2])] = provider
            panels += p

        return panels, providers


def _save_config(config, req, log, notices=None):
    """Try to save the config, and display either a success notice or a
    failure warning.
    """
    try:
        config.save()
        if notices is None:
            notices = [_("Your changes have been saved.")]
        for notice in notices:
            add_notice(req, notice)
    except Exception as e:
        log.error("Error writing to trac.ini: %s", exception_to_unicode(e))
        add_warning(req, _("Error writing to trac.ini, make sure it is "
                           "writable by the web server. Your changes have "
                           "not been saved."))


class BasicsAdminPanel(Component):

    implements(IAdminPanelProvider)

    request_handlers = ExtensionPoint(IRequestHandler)

    # IAdminPanelProvider methods

    def get_admin_panels(self, req):
        if 'TRAC_ADMIN' in req.perm('admin', 'general/basics'):
            yield ('general', _("General"), 'basics', _("Basic Settings"))

    def render_admin_panel(self, req, cat, page, path_info):
        valid_default_handlers = [handler.__class__.__name__
                                  for handler in self.request_handlers
                                  if is_valid_default_handler(handler)]
        if Locale:
            locale_ids = get_available_locales()
            locales = [Locale.parse(locale) for locale in locale_ids]
            # don't use str(locale) to prevent storing expanded locale
            # identifier, see #11258
            languages = sorted((id, locale.display_name)
                               for id, locale in zip(locale_ids, locales))
        else:
            locale_ids, locales, languages = [], [], []

        if req.method == 'POST':
            for option in ('name', 'url', 'descr'):
                self.config.set('project', option, req.args.get(option))

            default_handler = req.args.get('default_handler')
            self.config.set('trac', 'default_handler', default_handler)

            default_timezone = req.args.get('default_timezone')
            if default_timezone not in all_timezones:
                default_timezone = ''
            self.config.set('trac', 'default_timezone', default_timezone)

            default_language = req.args.get('default_language')
            if default_language not in locale_ids:
                default_language = ''
            self.config.set('trac', 'default_language', default_language)

            default_date_format = req.args.get('default_date_format')
            if default_date_format != 'iso8601':
                default_date_format = ''
            self.config.set('trac', 'default_date_format',
                            default_date_format)

            default_dateinfo_format = req.args.get('default_dateinfo_format')
            if default_dateinfo_format not in ('relative', 'absolute'):
                default_dateinfo_format = 'relative'
            self.config.set('trac', 'default_dateinfo_format',
                            default_dateinfo_format)

            _save_config(self.config, req, self.log)
            req.redirect(req.href.admin(cat, page))

        default_handler = self.config.get('trac', 'default_handler')
        default_timezone = self.config.get('trac', 'default_timezone')
        default_language = self.config.get('trac', 'default_language')
        default_date_format = self.config.get('trac', 'default_date_format')
        default_dateinfo_format = self.config.get('trac',
                                                  'default_dateinfo_format')

        data = {
            'default_handler': default_handler,
            'valid_default_handlers': sorted(valid_default_handlers),
            'default_timezone': default_timezone,
            'timezones': all_timezones,
            'has_pytz': pytz is not None,
            'default_language': default_language.replace('-', '_'),
            'languages': languages,
            'default_date_format': default_date_format,
            'default_dateinfo_format': default_dateinfo_format,
            'has_babel': Locale is not None,
        }
        Chrome(self.env).add_textarea_grips(req)
        return 'admin_basics.html', data


class LoggingAdminPanel(Component):

    implements(IAdminPanelProvider)

    # IAdminPanelProvider methods

    def get_admin_panels(self, req):
        if 'TRAC_ADMIN' in req.perm('admin', 'general/logging'):
            yield ('general', _("General"), 'logging', _("Logging"))

    def render_admin_panel(self, req, cat, page, path_info):
        log_type = self.env.log_type
        log_level = self.env.log_level
        log_file = self.env.log_file
        log_dir = self.env.log_dir

        log_types = [
            dict(name='none', label=_("None"),
                 selected=log_type == 'none', disabled=False),
            dict(name='stderr', label=_("Console"),
                 selected=log_type == 'stderr', disabled=False),
            dict(name='file', label=_("File"),
                 selected=log_type == 'file', disabled=False),
            dict(name='syslog', label=_("Syslog"),
                 selected=log_type in ('unix', 'syslog'),
                 disabled=os.name != 'posix'),
            dict(name='eventlog', label=_("Windows event log"),
                 selected=log_type in ('winlog', 'eventlog', 'nteventlog'),
                 disabled=os.name != 'nt'),
        ]

        if req.method == 'POST':
            changed = False

            new_type = req.args.get('log_type')
            if new_type not in [t['name'] for t in log_types]:
                raise TracError(
                    _("Unknown log type %(type)s", type=new_type),
                    _("Invalid log type")
                )
            new_file = req.args.get('log_file', 'trac.log')
            if not new_file:
                raise TracError(_("You must specify a log file"),
                                _("Missing field"))
            new_level = req.args.get('log_level')
            if new_level not in log.LOG_LEVELS:
                raise TracError(
                    _("Unknown log level %(level)s", level=new_level),
                    _("Invalid log level"))

            # Create logger to be sure the configuration is valid.
            new_file_path = new_file
            if not os.path.isabs(new_file_path):
                new_file_path = os.path.join(self.env.log_dir, new_file)
            try:
                logger, handler = \
                    self.env.create_logger(new_type, new_file_path, new_level,
                                           self.env.log_format)
            except Exception as e:
                add_warning(req,
                            tag_("Changes not saved. Logger configuration "
                                 "error: %(error)s. Inspect the log for more "
                                 "information.",
                                 error=tag.code(exception_to_unicode(e))))
                self.log.error("Logger configuration error: %s",
                               exception_to_unicode(e, traceback=True))
            else:
                handler.close()
                if new_type != log_type:
                    self.config.set('logging', 'log_type', new_type)
                    changed = True
                    log_type = new_type

                if log_type == 'none':
                    self.config.remove('logging', 'log_level')
                    changed = True
                else:
                    if new_level != log_level:
                        self.config.set('logging', 'log_level', new_level)
                        changed = True
                        log_level = new_level

                if log_type == 'file':
                    if new_file != log_file:
                        self.config.set('logging', 'log_file', new_file)
                        changed = True
                        log_file = new_file
                else:
                    self.config.remove('logging', 'log_file')
                    changed = True

            if changed:
                _save_config(self.config, req, self.log),
            req.redirect(req.href.admin(cat, page))

        # Order log levels by priority value, with aliases excluded.
        all_levels = sorted(log.LOG_LEVEL_MAP, key=log.LOG_LEVEL_MAP.get,
                            reverse=True)
        log_levels = [level for level in all_levels if level in log.LOG_LEVELS]

        data = {
            'type': log_type, 'types': log_types,
            'level': log_level, 'levels': log_levels,
            'file': log_file, 'dir': log_dir
        }
        return 'admin_logging.html', {'log': data}


class PermissionAdminPanel(Component):

    implements(IAdminPanelProvider, IPermissionRequestor)

    # IPermissionRequestor methods
    def get_permission_actions(self):
        actions = ['PERMISSION_GRANT', 'PERMISSION_REVOKE']
        return actions + [('PERMISSION_ADMIN', actions)]

    # IAdminPanelProvider methods
    def get_admin_panels(self, req):
        perm = req.perm('admin', 'general/perm')
        if 'PERMISSION_GRANT' in perm or 'PERMISSION_REVOKE' in perm:
            yield ('general', _("General"), 'perm', _("Permissions"))

    def render_admin_panel(self, req, cat, page, path_info):
        perm = PermissionSystem(self.env)
        all_actions = perm.get_actions()

        if req.method == 'POST':
            subject = req.args.get('subject', '').strip()
            target = req.args.get('target', '').strip()
            action = req.args.get('action')
            group = req.args.get('group', '').strip()

            if subject and subject.isupper() or \
                    group and group.isupper() or \
                    target and target.isupper():
                raise TracError(_("All upper-cased tokens are reserved for "
                                  "permission names."))

            # Grant permission to subject
            if 'add' in req.args and subject and action:
                req.perm('admin', 'general/perm').require('PERMISSION_GRANT')
                if action not in all_actions:
                    raise TracError(_("Unknown action"))
                req.perm.require(action)
                try:
                    perm.grant_permission(subject, action)
                except TracError as e:
                    add_warning(req, e)
                else:
                    add_notice(req, _("The subject %(subject)s has been "
                                      "granted the permission %(action)s.",
                                      subject=subject, action=action))

            # Add subject to group
            elif 'add' in req.args and subject and group:
                req.perm('admin', 'general/perm').require('PERMISSION_GRANT')
                for action in sorted(
                        perm.get_user_permissions(group, expand_meta=False)):
                    req.perm.require(action,
                        message=_("The subject %(subject)s was not added to "
                                  "the group %(group)s because the group has "
                                  "%(perm)s permission and users cannot grant "
                                  "permissions they don't possess.",
                                  subject=subject, group=group, perm=action))
                try:
                    perm.grant_permission(subject, group)
                except TracError as e:
                    add_warning(req, e)
                else:
                    add_notice(req, _("The subject %(subject)s has been "
                                      "added to the group %(group)s.",
                                      subject=subject, group=group))

            # Copy permissions to subject
            elif 'copy' in req.args and subject and target:
                req.perm('admin', 'general/perm').require('PERMISSION_GRANT')

                subject_permissions = perm.get_users_dict().get(subject, [])
                if not subject_permissions:
                    add_warning(req, _("The subject %(subject)s does not "
                                       "have any permissions.",
                                       subject=subject))

                for action in subject_permissions:
                    if action not in all_actions:  # plugin disabled?
                        self.log.warning("Skipped granting %s to %s: "
                                         "permission unavailable.",
                                         action, target)
                    else:
                        if action not in req.perm:
                            add_warning(req,
                                        _("The permission %(action)s was "
                                          "not granted to %(subject)s "
                                          "because users cannot grant "
                                          "permissions they don't possess.",
                                          action=action, subject=subject))
                            continue
                        try:
                            perm.grant_permission(target, action)
                        except PermissionExistsError:
                            pass
                        else:
                            add_notice(req, _("The subject %(subject)s has "
                                              "been granted the permission "
                                              "%(action)s.",
                                              subject=target, action=action))
                req.redirect(req.href.admin(cat, page))

            # Remove permissions action
            elif 'remove' in req.args and 'sel' in req.args:
                req.perm('admin', 'general/perm').require('PERMISSION_REVOKE')
                for key in req.args.getlist('sel'):
                    subject, action = key.split(':', 1)
                    subject = unicode_from_base64(subject)
                    action = unicode_from_base64(action)
                    if (subject, action) in perm.get_all_permissions():
                        perm.revoke_permission(subject, action)
                add_notice(req, _("The selected permissions have been "
                                  "revoked."))

            req.redirect(req.href.admin(cat, page))

        return 'admin_perms.html', {
            'actions': all_actions,
            'allowed_actions': [a for a in all_actions if a in req.perm],
            'perms': perm.get_users_dict(),
            'groups': perm.get_groups_dict(),
            'unicode_to_base64': unicode_to_base64
        }


class PluginAdminPanel(Component):

    implements(IAdminPanelProvider)

    # IAdminPanelProvider methods

    def get_admin_panels(self, req):
        if 'TRAC_ADMIN' in req.perm('admin', 'general/plugin'):
            yield ('general', _("General"), 'plugin', _("Plugins"))

    def render_admin_panel(self, req, cat, page, path_info):
        if req.method == 'POST':
            if 'install' in req.args:
                self._do_install(req)
            elif 'uninstall' in req.args:
                self._do_uninstall(req)
            else:
                self._do_update(req)
            anchor = ''
            if 'plugin' in req.args:
                anchor = '#no%d' % (req.args.getint('plugin') + 1)
            req.redirect(req.href.admin(cat, page) + anchor)

        return self._render_view(req)

    # Internal methods

    def _do_install(self, req):
        """Install a plugin."""
        if 'plugin_file' not in req.args:
            raise TracError(_("No file uploaded"))
        upload = req.args['plugin_file']
        if isinstance(upload, unicode) or not upload.filename:
            raise TracError(_("No file uploaded"))
        plugin_filename = upload.filename.replace('\\', '/').replace(':', '/')
        plugin_filename = os.path.basename(plugin_filename)
        if not plugin_filename:
            raise TracError(_("No file uploaded"))
        if not plugin_filename.endswith('.egg') and \
                not plugin_filename.endswith('.py'):
            raise TracError(_("Uploaded file is not a Python source file or "
                              "egg"))

        target_path = os.path.join(self.env.plugins_dir, plugin_filename)
        if os.path.isfile(target_path):
            raise TracError(_("Plugin %(name)s already installed",
                              name=plugin_filename))

        self.log.info("Installing plugin %s", plugin_filename)
        flags = os.O_CREAT + os.O_WRONLY + os.O_EXCL
        try:
            flags += os.O_BINARY
        except AttributeError:
            # OS_BINARY not available on every platform
            pass
        with os.fdopen(os.open(target_path, flags, 0o666), 'w') as target_file:
            shutil.copyfileobj(upload.file, target_file)
            self.log.info("Plugin %s installed to %s", plugin_filename,
                          target_path)
        # TODO: Validate that the uploaded file is a valid Trac plugin

        # Make the environment reset itself on the next request
        self.env.config.touch()

    def _do_uninstall(self, req):
        """Uninstall a plugin."""
        plugin_filename = req.args.get('plugin_filename')
        if not plugin_filename:
            return
        plugin_path = os.path.join(self.env.plugins_dir, plugin_filename)
        if not os.path.isfile(plugin_path):
            return
        self.log.info("Uninstalling plugin %s", plugin_filename)
        os.remove(plugin_path)

        # Make the environment reset itself on the next request
        self.env.config.touch()

    def _do_update(self, req):
        """Update component enable state."""
        components = req.args.getlist('component')
        enabled = req.args.getlist('enable')
        added, removed = [], []

        # FIXME: this needs to be more intelligent and minimize multiple
        # component names to prefix rules

        for component in components:
            is_enabled = bool(self.env.is_component_enabled(component))
            must_enable = component in enabled
            if is_enabled != must_enable:
                self.config.set('components', component,
                                'disabled' if is_enabled else 'enabled')
                self.log.info("%sabling component %s",
                              "Dis" if is_enabled else "En", component)
                if must_enable:
                    added.append(component)
                else:
                    removed.append(component)

        if added or removed:
            def make_list(items):
                parts = [item.rsplit('.', 1) for item in items]
                return tag.table(tag.tbody(
                    tag.tr(tag.td(c, class_='trac-name'),
                           tag.td('(%s.*)' % m, class_='trac-name'))
                    for m, c in parts), class_='trac-pluglist')

            added.sort()
            removed.sort()
            notices = []
            if removed:
                msg = ngettext("The following component has been disabled:",
                               "The following components have been disabled:",
                               len(removed))
                notices.append(tag(msg, make_list(removed)))
            if added:
                msg = ngettext("The following component has been enabled:",
                               "The following components have been enabled:",
                               len(added))
                notices.append(tag(msg, make_list(added)))

            # set the default value of options for only the enabled components
            for component in added:
                self.config.set_defaults(component=component)
            _save_config(self.config, req, self.log, notices)

    def _render_view(self, req):
        plugins = get_plugin_info(self.env, include_core=True)

        def safe_wiki_to_html(context, text):
            try:
                return format_to_html(self.env, context, text)
            except Exception as e:
                self.log.error("Unable to render component documentation: %s",
                               exception_to_unicode(e, traceback=True))
                return tag.pre(text)

        data = {
            'plugins': plugins, 'show': req.args.get('show'),
            'readonly': not os.access(self.env.plugins_dir,
                                      os.F_OK + os.W_OK),
            'safe_wiki_to_html': safe_wiki_to_html,
        }
        return 'admin_plugins.html', data
