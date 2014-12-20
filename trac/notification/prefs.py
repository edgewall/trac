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

import re
from operator import itemgetter
from pkg_resources import resource_filename

from trac.core import Component, implements, ExtensionPoint
from trac.notification.api import (INotificationDistributor,
                                   INotificationFormatter,
                                   INotificationSubscriber)
from trac.notification.model import Subscription
from trac.prefs.api import IPreferencePanelProvider
from trac.web.chrome import ITemplateProvider
from trac.util.translation import _


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
            'set-format': self._set_format
        }

    # IPreferencePanelProvider
    def get_preference_panels(self, req):
        yield ('notification', _('Notifications'))

    def render_preference_panel(self, req, panel, path_info=None):
        if req.method == 'POST':
            action_arg = req.args.get('action', '')
            m = re.match('^([^_]+)_(.+)', action_arg)
            if m:
                action, arg = m.groups()
                handler = self.post_handlers.get(action)
                if handler:
                    handler(arg, req)
            req.redirect(req.href.prefs('notification'))

        data = {'rules':{}, 'subscribers':[]}

        desc_map = {}
        defaults = []

        data['formatters'] = {}
        data['selected_format'] = {}
        data['adverbs'] = ('always', 'never')
        data['adverb_labels'] = dict(always=_("Notify"),
                                     never=_("Never notify"))

        for i in self.subscribers:
            if not i.description():
                continue
            if not req.session.authenticated and i.requires_authentication():
                continue
            data['subscribers'].append({
                'class': i.__class__.__name__,
                'description': i.description()
            })
            desc_map[i.__class__.__name__] = i.description()
            if hasattr(i, 'default_subscriptions'):
                defaults.extend(i.default_subscriptions())

        for distributor in self.distributors:
            for t in distributor.transports():
                data['rules'][t] = []
                styles = [s for f in self.formatters
                            for s, realm in f.get_supported_styles(t)]
                data['formatters'][t] = styles
                data['selected_format'][t] = styles[0]
                for r in Subscription.find_by_sid_and_distributor(self.env,
                        req.session.sid, req.session.authenticated, t):
                    if desc_map.get(r['class']):
                        data['rules'][t].append({
                            'id': r['id'],
                            'adverb': r['adverb'],
                            'description': desc_map[r['class']],
                            'priority': r['priority']
                        })
                        data['selected_format'][t] = r['format']

        data['default_rules'] = {}
        for r in sorted(defaults, key=itemgetter(3)):
            klass, dist, format, priority, adverb = r
            if not data['default_rules'].get(dist):
                data['default_rules'][dist] = []
            if desc_map.get(klass):
                data['default_rules'][dist].append({
                    'adverb': adverb,
                    'description': desc_map.get(klass)
                })

        return 'prefs_notification.html', dict(data=data)

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
        Subscription.delete(self.env, arg)

    def _move_rule(self, arg, req):
        (rule_id, new_priority) = arg.split('-')
        if int(new_priority) >= 1:
            Subscription.move(self.env, rule_id, int(new_priority))

    def _set_format(self, arg, req):
        Subscription.update_format_by_distributor_and_sid(self.env, arg,
                req.session.sid, req.session.authenticated,
                req.args['format-%s' % arg])

    # ITemplateProvider
    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        resource_dir = resource_filename('trac.notification', 'templates')
        return [resource_dir]