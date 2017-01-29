# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2014 Edgewall Software
# Copyright (C) 2004-2005 Daniel Lundin <daniel@edgewall.com>
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
# Author: Daniel Lundin <daniel@edgewall.com>

import pkg_resources
import re

from genshi.builder import tag

from trac.core import *
from trac.prefs.api import IPreferencePanelProvider
from trac.util import lazy
from trac.util.datefmt import all_timezones, get_timezone, localtz
from trac.util.translation import _, Locale, deactivate,\
                                  get_available_locales, make_activable
from trac.web.api import HTTPNotFound, IRequestHandler, \
                         is_valid_default_handler
from trac.web.chrome import Chrome, INavigationContributor, \
                            ITemplateProvider, add_notice, add_stylesheet


class PreferencesModule(Component):
    """Displays the preference panels and dispatch control to the
    individual panels"""

    implements(INavigationContributor, IRequestHandler, ITemplateProvider)

    panel_providers = ExtensionPoint(IPreferencePanelProvider)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'prefs'

    def get_navigation_items(self, req):
        panels = self._get_panels(req)[0]
        if panels:
            yield 'metanav', 'prefs', tag.a(_("Preferences"),
                                            href=req.href.prefs())

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match('/prefs(?:/([^/]+))?$', req.path_info)
        if match:
            req.args['panel_id'] = match.group(1)
            return True

    def process_request(self, req):
        if req.is_xhr and req.method == 'POST' and 'save_prefs' in req.args:
            self._do_save_xhr(req)

        panels, providers = self._get_panels(req)
        if not panels:
            raise HTTPNotFound(_("No preference panels available"))

        panels = []
        child_panels = {}
        providers = {}
        for provider in self.panel_providers:
            for panel in provider.get_preference_panels(req) or []:
                if len(panel) == 3:
                    name, label, parent = panel
                    child_panels.setdefault(parent, []).append((name, label))
                else:
                    name = panel[0]
                    panels.append(panel)
                providers[name] = provider
        panels = sorted(panels)

        panel_id = req.args.get('panel_id')
        if panel_id is None:
            panel_id = panels[1][0] \
                       if len(panels) > 1 and panels[0][0] == 'advanced' \
                       else panels[0][0]
        chosen_provider = providers.get(panel_id)
        if not chosen_provider:
            raise HTTPNotFound(_("Unknown preference panel '%(panel)s'",
                                 panel=panel_id))

        session_data = {
            'session': req.session,
            'settings': {'session': req.session,  # Compat: remove in 1.3.1
                         'session_id': req.session.sid},
        }

        # Render child preference panels.
        chrome = Chrome(self.env)
        children = []
        if child_panels.get(panel_id):
            for name, label in child_panels[panel_id]:
                ctemplate, cdata = provider.render_preference_panel(req, name)
                cdata.update(session_data)
                rendered = chrome.render_template(req, ctemplate, cdata,
                                                  fragment=True)
                children.append((name, label, rendered))

        template, data = \
            chosen_provider.render_preference_panel(req, panel_id)
        data.update(session_data)
        data.update({
            'active_panel': panel_id,
            'panels': panels,
            'children': children,
        })

        add_stylesheet(req, 'common/css/prefs.css')
        return template, data, None

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename('trac.prefs', 'templates')]

    # Internal methods

    def _get_panels(self, req):
        """Return a list of available preference panels."""
        panels = []
        providers = {}
        for provider in self.panel_providers:
            p = list(provider.get_preference_panels(req) or [])
            for panel in p:
                providers[panel[0]] = provider
            panels += p

        return panels, providers

    def _do_save_xhr(self, req):
        for key in req.args:
            if key not in ('save_prefs', 'panel_id', '__FORM_TOKEN'):
                req.session[key] = req.args[key]
        req.session.save()
        req.send_no_content()


class AdvancedPreferencePanel(Component):

    implements(IPreferencePanelProvider)

    _form_fields = ('newsid',)

    # IPreferencePanelProvider methods

    def get_preference_panels(self, req):
        if not req.authname or req.authname == 'anonymous':
            yield 'advanced', _("Advanced")

    def render_preference_panel(self, req, panel):
        if req.method == 'POST':
            if 'restore' in req.args:
                self._do_load(req)
            else:
                _do_save(req, panel, self._form_fields)
        return 'prefs_advanced.html', {'session_id': req.session.sid}

    def _do_load(self, req):
        if req.authname == 'anonymous':
            oldsid = req.args.get('loadsid')
            if oldsid:
                req.session.get_session(oldsid)
                add_notice(req, _("The session has been loaded."))


class GeneralPreferencePanel(Component):

    implements(IPreferencePanelProvider)

    _form_fields = ('name', 'email')

    # IPreferencePanelProvider methods

    def get_preference_panels(self, req):
        yield None, _("General")

    def render_preference_panel(self, req, panel):
        if req.method == 'POST':
            _do_save(req, panel, self._form_fields)
        return 'prefs_general.html', {}


class KeyBindingsPreferencePanel(Component):

    implements(IPreferencePanelProvider)

    _form_fields = ('accesskeys',)

    # IPreferencePanelProvider methods

    def get_preference_panels(self, req):
        yield 'keybindings', _("Keyboard Shortcuts")

    def render_preference_panel(self, req, panel):
        if req.method == 'POST':
            _do_save(req, panel, self._form_fields)
        return 'prefs_keybindings.html', {}


class LocalizationPreferencePanel(Component):

    implements(IPreferencePanelProvider)

    _form_fields = ('tz', 'lc_time', 'dateinfo', 'language')

    # IPreferencePanelProvider methods

    def get_preference_panels(self, req):
        yield 'localization', _("Localization")

    def render_preference_panel(self, req, panel):
        if req.method == 'POST':
            if Locale and \
                    req.args.get('language') != req.session.get('language'):
                # reactivate translations with new language setting
                # when changed
                del req.locale  # for re-negotiating locale
                deactivate()
                make_activable(lambda: req.locale, self.env.path)
            _do_save(req, panel, self._form_fields)

        data = {
            'timezones': all_timezones,
            'timezone': get_timezone,
            'localtz': localtz,
            'has_babel': False,
        }
        if Locale:
            locale_ids = get_available_locales()
            locales = [Locale.parse(locale) for locale in locale_ids]
            # use locale identifiers from get_available_locales() instead
            # of str(locale) to prevent storing expanded locale identifier
            # to session, e.g. zh_Hans_CN and zh_Hant_TW, since Babel 1.0.
            # see #11258.
            languages = sorted((id_, locale.display_name)
                               for id_, locale in zip(locale_ids, locales))
            data['locales'] = locales
            data['languages'] = languages
            data['has_babel'] = True
        return 'prefs_localization.html', data


class UserInterfacePreferencePanel(Component):

    implements(IPreferencePanelProvider)

    _request_handlers = ExtensionPoint(IRequestHandler)
    _form_fields = ('default_handler', 'ui.hide_help', 'ui.use_symbols')

    # IPreferencePanelProvider methods

    def get_preference_panels(self, req):
        yield 'userinterface', _("User Interface")

    def render_preference_panel(self, req, panel):
        if req.method == 'POST':
            _do_save(req, panel, self._form_fields)

        data = {
            'project_default_handler': self._project_default_handler,
            'valid_default_handlers': self._valid_default_handlers,
        }
        return 'prefs_userinterface.html', data

    # Internal methods

    @property
    def _project_default_handler(self):
        return self.config.get('trac', 'default_handler')

    @lazy
    def _valid_default_handlers(self):
        return sorted(handler.__class__.__name__
                      for handler in self._request_handlers
                      if is_valid_default_handler(handler))


def _do_save(req, panel, form_fields):
    for field in form_fields:
        val = req.args.get(field, '').strip()
        if val:
            if field == 'tz' and 'tz' in req.session and \
                    val not in all_timezones:
                del req.session['tz']
            elif field == 'newsid':
                req.session.change_sid(val)
            else:
                req.session[field] = val
        elif (field in req.args or field + '_cb' in req.args) and \
                field in req.session:
            del req.session[field]
    add_notice(req, _("Your preferences have been saved."))
    req.redirect(req.href.prefs(panel))
