# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
# Copyright (C) 2008 Stephen Hansen
# Copyright (C) 2009-2010 Robert Corsaro
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from operator import itemgetter
from pkg_resources import resource_filename

from genshi.builder import tag

from trac.core import Component, implements, ExtensionPoint
from trac.notification.api import (INotificationDistributor,
                                   INotificationFormatter,
                                   INotificationSubscriber,
                                   NotificationSystem)
from trac.notification.model import Subscription
from trac.prefs.api import IPreferencePanelProvider
from trac.web.chrome import Chrome, ITemplateProvider, add_notice
from trac.web.session import get_session_attribute
from trac.wiki.macros import WikiMacroBase
from trac.util import as_int
from trac.util.translation import _, cleandoc_


def get_preferred_format(env, sid, authenticated, transport):
    return get_session_attribute(env, sid, authenticated,
                                 'notification.format.%s' % transport)


class NotificationPreferences(Component):
    implements(IPreferencePanelProvider, ITemplateProvider)

    subscribers = ExtensionPoint(INotificationSubscriber)
    distributors = ExtensionPoint(INotificationDistributor)
    formatters = ExtensionPoint(INotificationFormatter)

    def __init__(self):
        self.post_handlers = {
            'add-rule': self._add_rule,
            'delete-rule': self._delete_rule,
            'move-rule': self._move_rule,
            'set-format': self._set_format,
            'replace': self._replace_rules,
        }

    # IPreferencePanelProvider methods

    def get_preference_panels(self, req):
        yield ('notification', _('Notifications'))

    def render_preference_panel(self, req, panel, path_info=None):
        if req.method == 'POST':
            action_arg = req.args.getfirst('action', '').split('_', 1)
            if len(action_arg) == 2:
                action, arg = action_arg
                handler = self.post_handlers.get(action)
                if handler:
                    handler(arg, req)
                    add_notice(req, _("Your preferences have been saved."))
            req.redirect(req.href.prefs('notification'))

        rules = {}
        subscribers = []
        formatters = {}
        selected_format = {}
        defaults = []

        for i in self.subscribers:
            description = i.description()
            if not description:
                continue
            if not req.session.authenticated and i.requires_authentication():
                continue
            subscribers.append({'class': i.__class__.__name__,
                                'description': description})
            if hasattr(i, 'default_subscriptions'):
                defaults.extend(i.default_subscriptions())
        desc_map = dict((s['class'], s['description']) for s in subscribers)

        for t in self._iter_transports():
            rules[t] = []
            formatters[t] = self._get_supported_styles(t)
            selected_format[t] = req.session.get('notification.format.%s' % t)
            for r in self._iter_rules(req, t):
                description = desc_map.get(r['class'])
                if description:
                    values = {'description': description}
                    values.update((key, r[key]) for key
                                                in ('id', 'adverb', 'class',
                                                    'priority'))
                    rules[t].append(values)

        default_rules = {}
        for r in sorted(defaults, key=itemgetter(3)):  # sort by priority
            klass, dist, format, priority, adverb = r
            default_rules.setdefault(dist, [])
            description = desc_map.get(klass)
            if description:
                default_rules[dist].append({'adverb': adverb,
                                            'description': description})

        data = {'rules': rules, 'subscribers': subscribers,
                'formatters': formatters, 'selected_format': selected_format,
                'default_rules': default_rules,
                'adverbs': ('always', 'never'),
                'adverb_labels': {'always': _("Notify"),
                                  'never': _("Never notify")}}
        Chrome(self.env).add_jquery_ui(req)
        return 'prefs_notification.html', dict(data=data)

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        resource_dir = resource_filename('trac.notification', 'templates')
        return [resource_dir]

    # Internal methods

    def _add_rule(self, arg, req):
        rule = Subscription(self.env)
        rule['sid'] = req.session.sid
        rule['authenticated'] = 1 if req.session.authenticated else 0
        rule['distributor'] = arg
        rule['format'] = req.args.get('format-%s' % arg, '')
        rule['adverb'] = req.args['new-adverb-%s' % arg]
        rule['class'] = req.args['new-rule-%s' % arg]
        Subscription.add(self.env, rule)

    def _delete_rule(self, arg, req):
        session = req.session
        Subscription.delete(self.env, arg, session.sid, session.authenticated)

    def _move_rule(self, arg, req):
        tokens = [as_int(val, 0) for val in arg.split('-', 1)]
        if len(tokens) == 2:
            rule_id, priority = tokens
            if rule_id > 0 and priority > 0:
                session = req.session
                Subscription.move(self.env, rule_id, priority, session.sid,
                                  session.authenticated)

    def _set_format(self, arg, req):
        format_ = req.args.getfirst('format-%s' % arg)
        format_ = self._normalize_format(format_, arg)
        req.session.set('notification.format.%s' % arg, format_, '')
        Subscription.update_format_by_distributor_and_sid(
            self.env, arg, req.session.sid, req.session.authenticated, format_)

    def _replace_rules(self, arg, req):
        subscriptions = []
        for transport in self._iter_transports():
            format_ = req.args.getfirst('format-' + transport)
            format_ = self._normalize_format(format_, transport)
            req.session.set('notification.format.%s' % transport, format_, '')
            adverbs = req.args.getlist('adverb-' + transport)
            classes = req.args.getlist('class-' + transport)
            for idx in xrange(min(len(adverbs), len(classes))):
                subscriptions.append({'distributor': transport,
                                      'format': format_,
                                      'adverb': adverbs[idx],
                                      'class': classes[idx]})

        sid = req.session.sid
        authenticated = req.session.authenticated
        with self.env.db_transaction:
            Subscription.replace_all(self.env, sid, authenticated,
                                     subscriptions)

    def _iter_rules(self, req, transport):
        session = req.session
        for r in Subscription.find_by_sid_and_distributor(
                self.env, session.sid, session.authenticated, transport):
            yield r

    def _iter_transports(self):
        for distributor in self.distributors:
            for transport in distributor.transports():
                yield transport

    def _get_supported_styles(self, transport):
        styles = set()
        for formatter in self.formatters:
            for style, realm_ in formatter.get_supported_styles(transport):
                styles.add(style)
        return sorted(styles)

    def _normalize_format(self, format_, transport):
        if format_:
            styles = self._get_supported_styles(transport)
            if format_ in styles:
                return format_
        return ''


class SubscriberListMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """Display a list of all installed notification subscribers, including
    documentation if available.

    Optionally, the name of a specific subscriber can be provided as an
    argument. In that case, only the documentation for that subscriber will
    be rendered.

    Note that this macro will not be able to display the documentation of
    subscribers if the `PythonOptimize` option is enabled for mod_python!
    """)

    def expand_macro(self, formatter, name, content):
        content = content.strip() if content else ''
        name_filter = content.strip('*')
        items = {}
        for subscriber in NotificationSystem(self.env).subscribers:
            name = subscriber.__class__.__name__
            if not name_filter or name.startswith(name_filter):
                items[name] = subscriber.description()

        return tag.div(class_='trac-subscriberlist')(
            tag.table(class_='wiki')(
                tag.thead(tag.tr(
                    tag.th(_("Subscriber")),
                    tag.th(_("Description")))),
                tag.tbody(
                    tag.tr(tag.td(tag.code(name)),
                           tag.td(items[name]),
                           class_='odd' if idx % 2 else 'even')
                    for idx, name in enumerate(sorted(items.keys())))))
