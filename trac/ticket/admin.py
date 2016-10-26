# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

from __future__ import with_statement

from datetime import datetime

from trac.admin.api import AdminCommandError, IAdminCommandProvider, \
                           IAdminPanelProvider, console_date_format, \
                           console_datetime_format, get_console_locale
from trac.core import *
from trac.resource import ResourceNotFound
from trac.ticket import model
from trac.ticket.api import TicketSystem
from trac.util import getuser
from trac.util.datefmt import (datetime_now, format_date, format_datetime,
                               get_datetime_format_hint, parse_date, user_time,
                               utc)
from trac.util.text import print_table, printout, exception_to_unicode
from trac.util.translation import _, N_, gettext
from trac.web.chrome import Chrome, add_notice, add_warning


class TicketAdminPanel(Component):

    implements(IAdminPanelProvider, IAdminCommandProvider)

    abstract = True

    _label = (N_('(Undefined)'), N_('(Undefined)'))

    # i18n note: use gettext() whenever refering to the above as text labels,
    #            and don't use it whenever using them as field names (after
    #            a call to `.lower()`)

    # IAdminPanelProvider methods

    def get_admin_panels(self, req):
        if 'TICKET_ADMIN' in req.perm('admin', 'ticket/' + self._type):
            yield ('ticket', _('Ticket System'), self._type,
                   gettext(self._label[1]))

    def render_admin_panel(self, req, cat, page, version):
        # Trap AssertionErrors and convert them to TracErrors
        try:
            return self._render_admin_panel(req, cat, page, version)
        except AssertionError, e:
            raise TracError(e)


def _save_config(config, req, log):
    """Try to save the config, and display either a success notice or a
    failure warning.
    """
    try:
        config.save()
        add_notice(req, _('Your changes have been saved.'))
    except Exception, e:
        log.error('Error writing to trac.ini: %s', exception_to_unicode(e))
        add_warning(req, _('Error writing to trac.ini, make sure it is '
                           'writable by the web server. Your changes have not '
                           'been saved.'))


class ComponentAdminPanel(TicketAdminPanel):

    _type = 'components'
    _label = (N_('Component'), N_('Components'))

    # TicketAdminPanel methods

    def _render_admin_panel(self, req, cat, page, component):
        # Detail view?
        if component:
            comp = model.Component(self.env, component)
            if req.method == 'POST':
                if req.args.get('save'):
                    comp.name = name = req.args.get('name')
                    comp.owner = req.args.get('owner')
                    comp.description = req.args.get('description')
                    try:
                        comp.update()
                    except self.env.db_exc.IntegrityError:
                        raise TracError(_('Component "%(name)s" already '
                                          'exists.', name=name))
                    add_notice(req, _('Your changes have been saved.'))
                    req.redirect(req.href.admin(cat, page))
                elif req.args.get('cancel'):
                    req.redirect(req.href.admin(cat, page))

            Chrome(self.env).add_wiki_toolbars(req)
            data = {'view': 'detail', 'component': comp}

        else:
            default = self.config.get('ticket', 'default_component')
            if req.method == 'POST':
                # Add Component
                if req.args.get('add') and req.args.get('name'):
                    name = req.args.get('name')
                    try:
                        comp = model.Component(self.env, name=name)
                    except ResourceNotFound:
                        comp = model.Component(self.env)
                        comp.name = name
                        if req.args.get('owner'):
                            comp.owner = req.args.get('owner')
                        comp.insert()
                        add_notice(req, _('The component "%(name)s" has been '
                                          'added.', name=name))
                        req.redirect(req.href.admin(cat, page))
                    else:
                        if comp.name is None:
                            raise TracError(_("Invalid component name."))
                        raise TracError(_('Component "%(name)s" already '
                                          'exists.', name=name))

                # Remove components
                elif req.args.get('remove'):
                    sel = req.args.get('sel')
                    if not sel:
                        raise TracError(_('No component selected'))
                    if not isinstance(sel, list):
                        sel = [sel]
                    with self.env.db_transaction:
                        for name in sel:
                            model.Component(self.env, name).delete()
                    add_notice(req, _("The selected components have been "
                                      "removed."))
                    req.redirect(req.href.admin(cat, page))

                # Set default component
                elif req.args.get('apply'):
                    name = req.args.get('default')
                    if name and name != default:
                        self.log.info("Setting default component to %s", name)
                        self.config.set('ticket', 'default_component', name)
                        _save_config(self.config, req, self.log)
                        req.redirect(req.href.admin(cat, page))

            data = {'view': 'list',
                    'components': list(model.Component.select(self.env)),
                    'default': default}

        owners = TicketSystem(self.env).get_allowed_owners()
        if owners is not None:
            owners.insert(0, '')
        data.update({'owners': owners})

        return 'admin_components.html', data

    # IAdminCommandProvider methods

    def get_admin_commands(self):
        yield ('component list', '',
               'Show available components',
               None, self._do_list)
        yield ('component add', '<name> [owner]',
               'Add a new component',
               self._complete_add, self._do_add)
        yield ('component rename', '<name> <newname>',
               'Rename a component',
               self._complete_remove_rename, self._do_rename)
        yield ('component remove', '<name>',
               'Remove/uninstall a component',
               self._complete_remove_rename, self._do_remove)
        yield ('component chown', '<name> <owner>',
               'Change component ownership',
               self._complete_chown, self._do_chown)

    def get_component_list(self):
        return [c.name for c in model.Component.select(self.env)]

    def get_user_list(self):
        return TicketSystem(self.env).get_allowed_owners()

    def _complete_add(self, args):
        if len(args) == 2:
            return self.get_user_list()

    def _complete_remove_rename(self, args):
        if len(args) == 1:
            return self.get_component_list()

    def _complete_chown(self, args):
        if len(args) == 1:
            return self.get_component_list()
        elif len(args) == 2:
            return self.get_user_list()

    def _do_list(self):
        print_table([(c.name, c.owner)
                     for c in model.Component.select(self.env)],
                    [_('Name'), _('Owner')])

    def _do_add(self, name, owner=None):
        component = model.Component(self.env)
        component.name = name
        component.owner = owner
        component.insert()

    def _do_rename(self, name, newname):
        component = model.Component(self.env, name)
        component.name = newname
        component.update()

    def _do_remove(self, name):
        model.Component(self.env, name).delete()

    def _do_chown(self, name, owner):
        component = model.Component(self.env, name)
        component.owner = owner
        component.update()


class MilestoneAdminPanel(TicketAdminPanel):

    _type = 'milestones'
    _label = (N_('Milestone'), N_('Milestones'))

    # IAdminPanelProvider methods

    def get_admin_panels(self, req):
        if 'MILESTONE_VIEW' in req.perm('admin', 'ticket/' + self._type):
            return TicketAdminPanel.get_admin_panels(self, req)

    # TicketAdminPanel methods

    def _render_admin_panel(self, req, cat, page, milestone):
        perm = req.perm('admin', 'ticket/' + self._type)
        # Detail view?
        if milestone:
            mil = model.Milestone(self.env, milestone)
            if req.method == 'POST':
                if req.args.get('save'):
                    perm.require('MILESTONE_MODIFY')
                    mil.name = name = req.args.get('name')
                    mil.due = mil.completed = None
                    due = req.args.get('duedate', '')
                    if due:
                        mil.due = user_time(req, parse_date, due,
                                            hint='datetime')
                    if req.args.get('completed', False):
                        completed = req.args.get('completeddate', '')
                        mil.completed = user_time(req, parse_date, completed,
                                                  hint='datetime')
                        if mil.completed > datetime_now(utc):
                            raise TracError(_('Completion date may not be in '
                                              'the future'),
                                            _('Invalid Completion Date'))
                    mil.description = req.args.get('description', '')
                    try:
                        mil.update(author=req.authname)
                    except self.env.db_exc.IntegrityError:
                        raise TracError(_('Milestone "%(name)s" already '
                                          'exists.', name=name))
                    add_notice(req, _('Your changes have been saved.'))
                    req.redirect(req.href.admin(cat, page))
                elif req.args.get('cancel'):
                    req.redirect(req.href.admin(cat, page))

            Chrome(self.env).add_wiki_toolbars(req)
            data = {'view': 'detail', 'milestone': mil}

        else:
            default = self.config.get('ticket', 'default_milestone')
            if req.method == 'POST':
                # Add Milestone
                if req.args.get('add') and req.args.get('name'):
                    perm.require('MILESTONE_CREATE')
                    name = req.args.get('name')
                    try:
                        mil = model.Milestone(self.env, name=name)
                    except ResourceNotFound:
                        mil = model.Milestone(self.env)
                        mil.name = name
                        if req.args.get('duedate'):
                            mil.due = user_time(req, parse_date,
                                                req.args.get('duedate'),
                                                hint='datetime')
                        mil.insert()
                        add_notice(req, _('The milestone "%(name)s" has been '
                                          'added.', name=name))
                        req.redirect(req.href.admin(cat, page))
                    else:
                        if mil.name is None:
                            raise TracError(_('Invalid milestone name.'))
                        raise TracError(_('Milestone "%(name)s" already '
                                          'exists.', name=name))

                # Remove milestone
                elif req.args.get('remove'):
                    perm.require('MILESTONE_DELETE')
                    sel = req.args.get('sel')
                    if not sel:
                        raise TracError(_('No milestone selected'))
                    if not isinstance(sel, list):
                        sel = [sel]
                    with self.env.db_transaction:
                        for name in sel:
                            milestone = model.Milestone(self.env, name)
                            milestone.move_tickets(None, req.authname,
                                                   "Milestone deleted")
                            milestone.delete()
                    add_notice(req, _("The selected milestones have been "
                                      "removed."))
                    req.redirect(req.href.admin(cat, page))

                # Set default milestone
                elif req.args.get('apply'):
                    name = req.args.get('default')
                    if name and name != default:
                        self.log.info("Setting default milestone to %s", name)
                        self.config.set('ticket', 'default_milestone', name)
                        _save_config(self.config, req, self.log)
                        req.redirect(req.href.admin(cat, page))

            # Get ticket count
            counts = dict(self.env.db_query("""
                    SELECT milestone, COUNT(milestone) FROM ticket
                    WHERE milestone != ''
                    GROUP BY milestone
                """))
            milestones = [(milestone, counts.get(milestone.name, 0))
                          for milestone in model.Milestone.select(self.env)]

            data = {'view': 'list',
                    'milestones': milestones,
                    'default': default}

        Chrome(self.env).add_jquery_ui(req)

        data.update({
            'datetime_hint': get_datetime_format_hint(req.lc_time),
        })
        return 'admin_milestones.html', data

    # IAdminCommandProvider methods

    def get_admin_commands(self):
        hints = {
           'datetime': get_datetime_format_hint(get_console_locale(self.env)),
           'iso8601': get_datetime_format_hint('iso8601'),
        }
        yield ('milestone list', '',
               "Show milestones",
               None, self._do_list)
        yield ('milestone add', '<name> [due]',
               "Add milestone",
               None, self._do_add)
        yield ('milestone rename', '<name> <newname>',
               "Rename milestone",
               self._complete_name, self._do_rename)
        yield ('milestone due', '<name> <due>',
               """Set milestone due date

               The <due> date must be specified in the "%(datetime)s"
               or "%(iso8601)s" (ISO 8601) format.
               Alternatively, "now" can be used to set the due date to the
               current time. To remove the due date from a milestone, specify
               an empty string ("").
               """ % hints,
               self._complete_name, self._do_due)
        yield ('milestone completed', '<name> <completed>',
               """Set milestone complete date

               The <completed> date must be specified in the "%(datetime)s"
               or "%(iso8601)s" (ISO 8601) format.
               Alternatively, "now" can be used to set the completion date to
               the current time. To remove the completion date from a
               milestone, specify an empty string ("").
               """ % hints,
               self._complete_name, self._do_completed)
        yield ('milestone remove', '<name>',
               "Remove milestone",
               self._complete_name, self._do_remove)

    def get_milestone_list(self):
        return [m.name for m in model.Milestone.select(self.env)]

    def _complete_name(self, args):
        if len(args) == 1:
            return self.get_milestone_list()

    def _do_list(self):
        print_table([(m.name,
                      format_date(m.due, console_date_format)
                      if m.due else None,
                      format_datetime(m.completed, console_datetime_format)
                      if m.completed else None)
                     for m in model.Milestone.select(self.env)],
                    [_("Name"), _("Due"), _("Completed")])

    def _do_add(self, name, due=None):
        milestone = model.Milestone(self.env)
        milestone.name = name
        if due is not None:
            milestone.due = parse_date(due, hint='datetime',
                                       locale=get_console_locale(self.env))
        milestone.insert()

    def _do_rename(self, name, newname):
        milestone = model.Milestone(self.env, name)
        milestone.name = newname
        milestone.update(author=getuser())

    def _do_due(self, name, due):
        milestone = model.Milestone(self.env, name)
        milestone.due = parse_date(due, hint='datetime',
                                   locale=get_console_locale(self.env)) \
                        if due else None
        milestone.update()

    def _do_completed(self, name, completed):
        milestone = model.Milestone(self.env, name)
        milestone.completed = parse_date(completed, hint='datetime',
                                         locale=get_console_locale(self.env)) \
                              if completed else None
        milestone.update()

    def _do_remove(self, name):
        model.Milestone(self.env, name).delete(author=getuser())


class VersionAdminPanel(TicketAdminPanel):

    _type = 'versions'
    _label = (N_('Version'), N_('Versions'))

    # TicketAdminPanel methods

    def _render_admin_panel(self, req, cat, page, version):
        # Detail view?
        if version:
            ver = model.Version(self.env, version)
            if req.method == 'POST':
                if req.args.get('save'):
                    ver.name = name = req.args.get('name')
                    if req.args.get('time'):
                        ver.time = user_time(req, parse_date,
                                             req.args.get('time'),
                                             hint='datetime')
                    else:
                        ver.time = None # unset
                    ver.description = req.args.get('description')
                    try:
                        ver.update()
                    except self.env.db_exc.IntegrityError:
                        raise TracError(_('Version "%(name)s" already '
                                          'exists.', name=name))

                    add_notice(req, _('Your changes have been saved.'))
                    req.redirect(req.href.admin(cat, page))
                elif req.args.get('cancel'):
                    req.redirect(req.href.admin(cat, page))

            Chrome(self.env).add_wiki_toolbars(req)
            data = {'view': 'detail', 'version': ver}

        else:
            default = self.config.get('ticket', 'default_version')
            if req.method == 'POST':
                # Add Version
                if req.args.get('add') and req.args.get('name'):
                    name = req.args.get('name')
                    try:
                        ver = model.Version(self.env, name=name)
                    except ResourceNotFound:
                        ver = model.Version(self.env)
                        ver.name = name
                        if req.args.get('time'):
                            ver.time = user_time(req, parse_date,
                                                 req.args.get('time'),
                                                 hint='datetime')
                        ver.insert()
                        add_notice(req, _('The version "%(name)s" has been '
                                          'added.', name=name))
                        req.redirect(req.href.admin(cat, page))
                    else:
                        if ver.name is None:
                            raise TracError(_("Invalid version name."))
                        raise TracError(_('Version "%(name)s" already '
                                          'exists.', name=name))

                # Remove versions
                elif req.args.get('remove'):
                    sel = req.args.get('sel')
                    if not sel:
                        raise TracError(_("No version selected"))
                    if not isinstance(sel, list):
                        sel = [sel]
                    with self.env.db_transaction:
                        for name in sel:
                            ver = model.Version(self.env, name)
                            ver.delete()
                    add_notice(req, _("The selected versions have been "
                                      "removed."))
                    req.redirect(req.href.admin(cat, page))

                # Set default version
                elif req.args.get('apply'):
                    name = req.args.get('default')
                    if name and name != default:
                        self.log.info("Setting default version to %s", name)
                        self.config.set('ticket', 'default_version', name)
                        _save_config(self.config, req, self.log)
                        req.redirect(req.href.admin(cat, page))

            data = {'view': 'list',
                    'versions': list(model.Version.select(self.env)),
                    'default': default}

        Chrome(self.env).add_jquery_ui(req)

        data.update({
            'datetime_hint': get_datetime_format_hint(req.lc_time),
        })
        return 'admin_versions.html', data

    # IAdminCommandProvider methods

    def get_admin_commands(self):
        hints = {
           'datetime': get_datetime_format_hint(get_console_locale(self.env)),
           'iso8601': get_datetime_format_hint('iso8601'),
        }
        yield ('version list', '',
               "Show versions",
               None, self._do_list)
        yield ('version add', '<name> [time]',
               "Add version",
               None, self._do_add)
        yield ('version rename', '<name> <newname>',
               "Rename version",
               self._complete_name, self._do_rename)
        yield ('version time', '<name> <time>',
               """Set version date

               The <time> must be specified in the "%(datetime)s"
               or "%(iso8601)s" (ISO 8601) format.
               Alternatively, "now" can be used to set the version date to
               the current time. To remove the date from a version, specify
               an empty string ("").
               """ % hints,
               self._complete_name, self._do_time)
        yield ('version remove', '<name>',
               "Remove version",
               self._complete_name, self._do_remove)

    def get_version_list(self):
        return [v.name for v in model.Version.select(self.env)]

    def _complete_name(self, args):
        if len(args) == 1:
            return self.get_version_list()

    def _do_list(self):
        print_table([(v.name,
                      format_date(v.time, console_date_format)
                      if v.time else None)
                    for v in model.Version.select(self.env)],
                    [_("Name"), _("Time")])

    def _do_add(self, name, time=None):
        version = model.Version(self.env)
        version.name = name
        if time is not None:
            version.time = parse_date(time, hint='datetime',
                                      locale=get_console_locale(self.env)) \
                           if time else None
        version.insert()

    def _do_rename(self, name, newname):
        version = model.Version(self.env, name)
        version.name = newname
        version.update()

    def _do_time(self, name, time):
        version = model.Version(self.env, name)
        version.time = parse_date(time, hint='datetime',
                                  locale=get_console_locale(self.env)) \
                       if time else None
        version.update()

    def _do_remove(self, name):
        model.Version(self.env, name).delete()


class AbstractEnumAdminPanel(TicketAdminPanel):

    abstract = True

    _type = 'unknown'
    _enum_cls = None

    # TicketAdminPanel methods

    def _render_admin_panel(self, req, cat, page, path_info):
        label = [gettext(each) for each in self._label]
        data = {'label_singular': label[0], 'label_plural': label[1],
                'type': self._type}

        # Detail view?
        if path_info:
            enum = self._enum_cls(self.env, path_info)
            if req.method == 'POST':
                if req.args.get('save'):
                    enum.name = name = req.args.get('name')
                    try:
                        enum.update()
                    except self.env.db_exc.IntegrityError:
                        raise TracError(_('%(type)s value "%(name)s" already '
                                          'exists', type=label[0], name=name))
                    add_notice(req, _("Your changes have been saved."))
                    req.redirect(req.href.admin(cat, page))
                elif req.args.get('cancel'):
                    req.redirect(req.href.admin(cat, page))
            data.update({'view': 'detail', 'enum': enum})

        else:
            default = self.config.get('ticket', 'default_%s' % self._type)
            if req.method == 'POST':
                # Add enum
                if req.args.get('add') and req.args.get('name'):
                    name = req.args.get('name')
                    try:
                        enum = self._enum_cls(self.env, name=name)
                    except ResourceNotFound:
                        enum = self._enum_cls(self.env)
                        enum.name = name
                        enum.insert()
                        add_notice(req, _('The %(field)s value "%(name)s" has '
                                          'been added.',
                                          field=label[0], name=name))
                        req.redirect(req.href.admin(cat, page))
                    else:
                        if enum.name is None:
                            raise TracError(_("Invalid %(type)s value.",
                                              type=label[0]))
                        raise TracError(_('%(type)s value "%(name)s" already '
                                          'exists', type=label[0], name=name))

                # Remove enums
                elif req.args.get('remove'):
                    sel = req.args.get('sel')
                    if not sel:
                        raise TracError(_("No %s selected") % self._type)
                    if not isinstance(sel, list):
                        sel = [sel]
                    with self.env.db_transaction:
                        for name in sel:
                            self._enum_cls(self.env, name).delete()
                    add_notice(req, _("The selected %(field)s values have "
                                      "been removed.", field=label[0]))
                    req.redirect(req.href.admin(cat, page))

                # Apply changes
                elif req.args.get('apply'):
                    changed = False

                    # Set default value
                    name = req.args.get('default')
                    if name and name != default:
                        self.log.info("Setting default %s to %s",
                                      self._type, name)
                        self.config.set('ticket', 'default_%s' % self._type,
                                        name)
                        try:
                            self.config.save()
                            changed = True
                        except Exception, e:
                            self.log.error("Error writing to trac.ini: %s",
                                           exception_to_unicode(e))
                            add_warning(req,
                                        _("Error writing to trac.ini, make "
                                          "sure it is writable by the web "
                                          "server. The default value has not "
                                          "been saved."))

                    # Change enum values
                    order = dict([(str(int(key[6:])),
                                   str(int(req.args.get(key)))) for key
                                  in req.args.keys()
                                  if key.startswith('value_')])
                    values = dict([(val, True) for val in order.values()])
                    if len(order) != len(values):
                        raise TracError(_("Order numbers must be unique"))
                    with self.env.db_transaction:
                        for enum in self._enum_cls.select(self.env):
                            new_value = order[enum.value]
                            if new_value != enum.value:
                                enum.value = new_value
                                enum.update()
                                changed = True

                    if changed:
                        add_notice(req, _("Your changes have been saved."))
                    req.redirect(req.href.admin(cat, page))

            data.update(dict(enums=list(self._enum_cls.select(self.env)),
                             default=default, view='list'))
        return 'admin_enums.html', data

    # IAdminCommandProvider methods

    _command_help = {
        'list': 'Show possible ticket %s',
        'add': 'Add a %s value option',
        'change': 'Change a %s value',
        'remove': 'Remove a %s value',
        'order': 'Move a %s value up or down in the list',
    }

    def get_admin_commands(self):
        enum_type = getattr(self, '_command_type', self._type)
        label = tuple(each.lower() for each in self._label)
        yield ('%s list' % enum_type, '',
               self._command_help['list'] % label[1],
               None, self._do_list)
        yield ('%s add' % enum_type, '<value>',
               self._command_help['add'] % label[0],
               None, self._do_add)
        yield ('%s change' % enum_type, '<value> <newvalue>',
               self._command_help['change'] % label[0],
               self._complete_change_remove, self._do_change)
        yield ('%s remove' % enum_type, '<value>',
               self._command_help['remove'] % label[0],
               self._complete_change_remove, self._do_remove)
        yield ('%s order' % enum_type, '<value> up|down',
               self._command_help['order'] % label[0],
               self._complete_order, self._do_order)

    def get_enum_list(self):
        return [e.name for e in self._enum_cls.select(self.env)]

    def _complete_change_remove(self, args):
        if len(args) == 1:
            return self.get_enum_list()

    def _complete_order(self, args):
        if len(args) == 1:
            return self.get_enum_list()
        elif len(args) == 2:
            return ['up', 'down']

    def _do_list(self):
        print_table([(e.name,) for e in self._enum_cls.select(self.env)],
                    [_('Possible Values')])

    def _do_add(self, name):
        enum = self._enum_cls(self.env)
        enum.name = name
        enum.insert()

    def _do_change(self, name, newname):
        enum = self._enum_cls(self.env, name)
        enum.name = newname
        enum.update()

    def _do_remove(self, value):
        self._enum_cls(self.env, value).delete()

    def _do_order(self, name, up_down):
        if up_down not in ('up', 'down'):
            raise AdminCommandError(_("Invalid up/down value: %(value)s",
                                      value=up_down))
        direction = -1 if up_down == 'up' else 1
        enum1 = self._enum_cls(self.env, name)
        enum1.value = int(float(enum1.value) + direction)
        for enum2 in self._enum_cls.select(self.env):
            if int(float(enum2.value)) == enum1.value:
                enum2.value = int(float(enum2.value) - direction)
                break
        else:
            return
        with self.env.db_transaction:
            enum1.update()
            enum2.update()


class PriorityAdminPanel(AbstractEnumAdminPanel):
    _type = 'priority'
    _enum_cls = model.Priority
    _label = (N_('Priority'), N_('Priorities'))


class ResolutionAdminPanel(AbstractEnumAdminPanel):
    _type = 'resolution'
    _enum_cls = model.Resolution
    _label = (N_('Resolution'), N_('Resolutions'))


class SeverityAdminPanel(AbstractEnumAdminPanel):
    _type = 'severity'
    _enum_cls = model.Severity
    _label = (N_('Severity'), N_('Severities'))


class TicketTypeAdminPanel(AbstractEnumAdminPanel):
    _type = 'type'
    _enum_cls = model.Type
    _label = (N_('Ticket Type'), N_('Ticket Types'))

    _command_type = 'ticket_type'
    _command_help = {
        'list': 'Show possible %s',
        'add': 'Add a %s',
        'change': 'Change a %s',
        'remove': 'Remove a %s',
        'order': 'Move a %s up or down in the list',
    }


class TicketAdmin(Component):
    """trac-admin command provider for ticket administration."""

    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods

    def get_admin_commands(self):
        yield ('ticket remove', '<number>',
               'Remove ticket',
               None, self._do_remove)

    def _do_remove(self, number):
        try:
            number = int(number)
        except ValueError:
            raise AdminCommandError(_('<number> must be a number'))
        with self.env.db_transaction:
            model.Ticket(self.env, number).delete()
        printout(_('Ticket #%(num)s and all associated data removed.',
                   num=number))
