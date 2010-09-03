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

from datetime import datetime

from trac.admin import *
from trac.core import *
from trac.perm import PermissionSystem
from trac.resource import ResourceNotFound
from trac.ticket import model
from trac.util import getuser
from trac.util.datefmt import utc, parse_date, get_datetime_format_hint, \
                              format_date, format_datetime
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
        if 'TICKET_ADMIN' in req.perm:
            yield ('ticket', _('Ticket System'), self._type,
                   gettext(self._label[1]))

    def render_admin_panel(self, req, cat, page, version):
        req.perm.require('TICKET_ADMIN')
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
                    comp.name = req.args.get('name')
                    comp.owner = req.args.get('owner')
                    comp.description = req.args.get('description')
                    comp.update()
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
                            raise TracError(_('Invalid component name.'))
                        raise TracError(_('Component %(name)s already exists.',
                                          name=name))

                # Remove components
                elif req.args.get('remove'):
                    sel = req.args.get('sel')
                    if not sel:
                        raise TracError(_('No component selected'))
                    if not isinstance(sel, list):
                        sel = [sel]
                    @self.env.with_transaction()
                    def do_remove(db):
                        for name in sel:
                            comp = model.Component(self.env, name, db=db)
                            comp.delete()
                    add_notice(req, _('The selected components have been '
                                      'removed.'))
                    req.redirect(req.href.admin(cat, page))

                # Set default component
                elif req.args.get('apply'):
                    name = req.args.get('default')
                    if name and name != default:
                        self.log.info('Setting default component to %s', name)
                        self.config.set('ticket', 'default_component', name)
                        _save_config(self.config, req, self.log)
                        req.redirect(req.href.admin(cat, page))

            data = {'view': 'list',
                    'components': model.Component.select(self.env),
                    'default': default}

        if self.config.getbool('ticket', 'restrict_owner'):
            perm = PermissionSystem(self.env)
            def valid_owner(username):
                return perm.get_user_permissions(username).get('TICKET_MODIFY')
            data['owners'] = [username for username, name, email
                              in self.env.get_known_users()
                              if valid_owner(username)]
            data['owners'].insert(0, '')
            data['owners'].sort()
        else:
            data['owners'] = None

        return 'admin_components.html', data

    # IAdminCommandProvider methods
    
    def get_admin_commands(self):
        yield ('component list', '',
               'Show available components',
               None, self._do_list)
        yield ('component add', '<name> <owner>',
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
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT DISTINCT username FROM permission")
        return [row[0] for row in cursor]
    
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
    
    def _do_add(self, name, owner):
        component = model.Component(self.env)
        component.name = name
        component.owner = owner
        component.insert()
    
    def _do_rename(self, name, newname):
        @self.env.with_transaction()
        def do_rename(db):
            component = model.Component(self.env, name, db=db)
            component.name = newname
            component.update()
    
    def _do_remove(self, name):
        @self.env.with_transaction()
        def do_remove(db):
            component = model.Component(self.env, name, db=db)
            component.delete()
    
    def _do_chown(self, name, owner):
        @self.env.with_transaction()
        def do_chown(db):
            component = model.Component(self.env, name, db=db)
            component.owner = owner
            component.update()


class MilestoneAdminPanel(TicketAdminPanel):

    _type = 'milestones'
    _label = (N_('Milestone'), N_('Milestones'))

    # IAdminPanelProvider methods

    def get_admin_panels(self, req):
        if 'MILESTONE_VIEW' in req.perm:
            return TicketAdminPanel.get_admin_panels(self, req)
        return iter([])

    # TicketAdminPanel methods

    def _render_admin_panel(self, req, cat, page, milestone):
        req.perm.require('MILESTONE_VIEW')
        
        # Detail view?
        if milestone:
            mil = model.Milestone(self.env, milestone)
            if req.method == 'POST':
                if req.args.get('save'):
                    req.perm.require('MILESTONE_MODIFY')
                    mil.name = req.args.get('name')
                    mil.due = mil.completed = None
                    due = req.args.get('duedate', '')
                    if due:
                        mil.due = parse_date(due, req.tz, 'datetime')
                    if req.args.get('completed', False):
                        completed = req.args.get('completeddate', '')
                        mil.completed = parse_date(completed, req.tz,
                                                   'datetime')
                        if mil.completed > datetime.now(utc):
                            raise TracError(_('Completion date may not be in '
                                              'the future'),
                                            _('Invalid Completion Date'))
                    mil.description = req.args.get('description', '')
                    mil.update()
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
                    req.perm.require('MILESTONE_CREATE')
                    name = req.args.get('name')
                    try:
                        mil = model.Milestone(self.env, name=name)
                    except ResourceNotFound:
                        mil = model.Milestone(self.env)
                        mil.name = name
                        if req.args.get('duedate'):
                            mil.due = parse_date(req.args.get('duedate'),
                                                 req.tz, 'datetime')
                        mil.insert()
                        add_notice(req, _('The milestone "%(name)s" has been '
                                          'added.', name=name))
                        req.redirect(req.href.admin(cat, page))
                    else:
                        if mil.name is None:
                            raise TracError(_('Invalid milestone name.'))
                        raise TracError(_('Milestone %(name)s already exists.',
                                          name=name))

                # Remove milestone
                elif req.args.get('remove'):
                    req.perm.require('MILESTONE_DELETE')
                    sel = req.args.get('sel')
                    if not sel:
                        raise TracError(_('No milestone selected'))
                    if not isinstance(sel, list):
                        sel = [sel]
                    @self.env.with_transaction()
                    def do_remove(db):
                        for name in sel:
                            mil = model.Milestone(self.env, name, db=db)
                            mil.delete(author=req.authname)
                    add_notice(req, _('The selected milestones have been '
                                      'removed.'))
                    req.redirect(req.href.admin(cat, page))

                # Set default milestone
                elif req.args.get('apply'):
                    name = req.args.get('default')
                    if name and name != default:
                        self.log.info('Setting default milestone to %s', name)
                        self.config.set('ticket', 'default_milestone', name)
                        _save_config(self.config, req, self.log)
                        req.redirect(req.href.admin(cat, page))

            # Get ticket count
            db = self.env.get_db_cnx()
            cursor = db.cursor()
            milestones = []
            for milestone in model.Milestone.select(self.env, db=db):
                cursor.execute("SELECT COUNT(*) FROM ticket "
                               "WHERE milestone=%s", (milestone.name, ))
                milestones.append((milestone, cursor.fetchone()[0]))
            
            data = {'view': 'list',
                    'milestones': milestones,
                    'default': default}

        data.update({
            'datetime_hint': get_datetime_format_hint()
        })
        return 'admin_milestones.html', data

    # IAdminCommandProvider methods
    
    def get_admin_commands(self):
        yield ('milestone list', '',
               'Show milestones',
               None, self._do_list)
        yield ('milestone add', '<name> [due]',
               'Add milestone',
               None, self._do_add)
        yield ('milestone rename', '<name> <newname>',
               'Rename milestone',
               self._complete_name, self._do_rename)
        yield ('milestone due', '<name> <due>',
               """Set milestone due date
               
               The <due> date must be specified in the "%s" format.
               Alternatively, "now" can be used to set the due date to the
               current time. To remove the due date from a milestone, specify
               an empty string ("").
               """ % console_date_format_hint,
               self._complete_name, self._do_due)
        yield ('milestone completed', '<name> <completed>',
               """Set milestone complete date
               
               The <completed> date must be specified in the "%s" format.
               Alternatively, "now" can be used to set the completion date to
               the current time. To remove the completion date from a
               milestone, specify an empty string ("").
               """ % console_date_format_hint,
               self._complete_name, self._do_completed)
        yield ('milestone remove', '<name>',
               'Remove milestone',
               self._complete_name, self._do_remove)
    
    def get_milestone_list(self):
        return [m.name for m in model.Milestone.select(self.env)]
    
    def _complete_name(self, args):
        if len(args) == 1:
            return self.get_milestone_list()
    
    def _do_list(self):
        print_table([(m.name, m.due and
                        format_date(m.due, console_date_format),
                      m.completed and
                        format_datetime(m.completed, console_datetime_format))
                     for m in model.Milestone.select(self.env)],
                    [_('Name'), _('Due'), _('Completed')])
    
    def _do_add(self, name, due=None):
        milestone = model.Milestone(self.env)
        milestone.name = name
        if due is not None:
            milestone.due = parse_date(due, hint='datetime')
        milestone.insert()
    
    def _do_rename(self, name, newname):
        @self.env.with_transaction()
        def do_rename(db):
            milestone = model.Milestone(self.env, name, db=db)
            milestone.name = newname
            milestone.update()
    
    def _do_due(self, name, due):
        @self.env.with_transaction()
        def do_due(db):
            milestone = model.Milestone(self.env, name, db=db)
            milestone.due = due and parse_date(due, hint='datetime')
            milestone.update()
    
    def _do_completed(self, name, completed):
        @self.env.with_transaction()
        def do_completed(db):
            milestone = model.Milestone(self.env, name, db=db)
            milestone.completed = completed and parse_date(completed,
                                                           hint='datetime')
            milestone.update()
    
    def _do_remove(self, name):
        @self.env.with_transaction()
        def do_remove(db):
            milestone = model.Milestone(self.env, name, db=db)
            milestone.delete(author=getuser())


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
                    ver.name = req.args.get('name')
                    if req.args.get('time'):
                        ver.time = parse_date(req.args.get('time'), req.tz,
                                              'datetime')
                    else:
                        ver.time = None # unset
                    ver.description = req.args.get('description')
                    ver.update()
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
                            ver.time = parse_date(req.args.get('time'),
                                                  req.tz, 'datetime')
                        ver.insert()
                        add_notice(req, _('The version "%(name)s" has been '
                                          'added.', name=name))
                        req.redirect(req.href.admin(cat, page))
                    else:
                        if ver.name is None:
                            raise TracError(_('Invalid version name.'))
                        raise TracError(_('Version %(name)s already exists.',
                                          name=name))
                         
                # Remove versions
                elif req.args.get('remove'):
                    sel = req.args.get('sel')
                    if not sel:
                        raise TracError(_('No version selected'))
                    if not isinstance(sel, list):
                        sel = [sel]
                    @self.env.with_transaction()
                    def do_remove(db):
                        for name in sel:
                            ver = model.Version(self.env, name, db=db)
                            ver.delete()
                    add_notice(req, _('The selected versions have been '
                                      'removed.'))
                    req.redirect(req.href.admin(cat, page))

                # Set default version
                elif req.args.get('apply'):
                    name = req.args.get('default')
                    if name and name != default:
                        self.log.info('Setting default version to %s', name)
                        self.config.set('ticket', 'default_version', name)
                        _save_config(self.config, req, self.log)
                        req.redirect(req.href.admin(cat, page))

            data = {'view': 'list',
                    'versions': model.Version.select(self.env),
                    'default': default}

        data.update({
            'datetime_hint': get_datetime_format_hint()
        })
        return 'admin_versions.html', data

    # IAdminCommandProvider methods
    
    def get_admin_commands(self):
        yield ('version list', '',
               'Show versions',
               None, self._do_list)
        yield ('version add', '<name> [time]',
               'Add version',
               None, self._do_add)
        yield ('version rename', '<name> <newname>',
               'Rename version',
               self._complete_name, self._do_rename)
        yield ('version time', '<name> <time>',
               """Set version date
               
               The <time> must be specified in the "%s" format. Alternatively,
               "now" can be used to set the version date to the current time.
               To remove the date from a version, specify an empty string
               ("").
               """ % console_date_format_hint,
               self._complete_name, self._do_time)
        yield ('version remove', '<name>',
               'Remove version',
               self._complete_name, self._do_remove)
    
    def get_version_list(self):
        return [v.name for v in model.Version.select(self.env)]
    
    def _complete_name(self, args):
        if len(args) == 1:
            return self.get_version_list()
    
    def _do_list(self):
        print_table([(v.name,
                      v.time and format_date(v.time, console_date_format))
                     for v in model.Version.select(self.env)],
                    [_('Name'), _('Time')])
    
    def _do_add(self, name, time=None):
        version = model.Version(self.env)
        version.name = name
        if time is not None:
            version.time = time and parse_date(time, hint='datetime')
        version.insert()
    
    def _do_rename(self, name, newname):
        @self.env.with_transaction()
        def do_rename(db):
            version = model.Version(self.env, name, db=db)
            version.name = newname
            version.update()
    
    def _do_time(self, name, time):
        @self.env.with_transaction()
        def do_time(db):
            version = model.Version(self.env, name, db=db)
            version.time = time and parse_date(time, hint='datetime')
            version.update()
    
    def _do_remove(self, name):
        @self.env.with_transaction()
        def do_remove(db):
            version = model.Version(self.env, name, db=db)
            version.delete()


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
                    enum.name = req.args.get('name')
                    enum.update()
                    add_notice(req, _('Your changes have been saved.'))
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
                    except:
                        enum = self._enum_cls(self.env)
                        enum.name = name
                        enum.insert()
                        add_notice(req, _('The %(field)s value "%(name)s" has '
                                          'been added.',
                                          field=label[0], name=name))
                        req.redirect(req.href.admin(cat, page))
                    else:
                        if enum.name is None:
                            raise TracError(_('Invalid %(type)s value.',
                                              type=label[0]))
                        raise TracError(_('%(type)s value "%(name)s" already '
                                          'exists', type=label[0], name=name))

                # Remove enums
                elif req.args.get('remove'):
                    sel = req.args.get('sel')
                    if not sel:
                        raise TracError(_('No %s selected') % self._type)
                    if not isinstance(sel, list):
                        sel = [sel]
                    @self.env.with_transaction()
                    def do_remove(db):
                        for name in sel:
                            enum = self._enum_cls(self.env, name, db=db)
                            enum.delete()
                    add_notice(req, _('The selected %(field)s values have '
                                      'been removed.', field=label[0]))
                    req.redirect(req.href.admin(cat, page))

                # Apply changes
                elif req.args.get('apply'):
                    changed = [False]
                    
                    # Set default value
                    name = req.args.get('default')
                    if name and name != default:
                        self.log.info('Setting default %s to %s',
                                      self._type, name)
                        self.config.set('ticket', 'default_%s' % self._type,
                                        name)
                        try:
                            self.config.save()
                            changed[0] = True
                        except Exception, e:
                            self.log.error('Error writing to trac.ini: %s',
                                           exception_to_unicode(e))
                            add_warning(req,
                                        _('Error writing to trac.ini, make '
                                          'sure it is writable by the web '
                                          'server. The default value has not '
                                          'been saved.'))

                    # Change enum values
                    order = dict([(str(int(key[6:])), 
                                   str(int(req.args.get(key)))) for key
                                  in req.args.keys()
                                  if key.startswith('value_')])
                    values = dict([(val, True) for val in order.values()])
                    if len(order) != len(values):
                        raise TracError(_('Order numbers must be unique'))
                    @self.env.with_transaction()
                    def do_change(db):
                        for enum in self._enum_cls.select(self.env, db=db):
                            new_value = order[enum.value]
                            if new_value != enum.value:
                                enum.value = new_value
                                enum.update()
                                changed[0] = True

                    if changed[0]:
                        add_notice(req, _('Your changes have been saved.'))
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
        @self.env.with_transaction()
        def do_change(db):
            enum = self._enum_cls(self.env, name, db=db)
            enum.name = newname
            enum.update()
    
    def _do_remove(self, value):
        @self.env.with_transaction()
        def do_remove(db):
            enum = self._enum_cls(self.env, value, db=db)
            enum.delete()
    
    def _do_order(self, name, up_down):
        if up_down not in ('up', 'down'):
            raise AdminCommandError(_("Invalid up/down value: %(value)s",
                                      value=up_down))
        direction = up_down == 'up' and -1 or 1
        db = self.env.get_db_cnx()
        enum1 = self._enum_cls(self.env, name, db=db)
        enum1.value = int(float(enum1.value) + direction)
        for enum2 in self._enum_cls.select(self.env, db=db):
            if int(float(enum2.value)) == enum1.value:
                enum2.value = int(float(enum2.value) - direction)
                break
        else:
            return
        @self.env.with_transaction()
        def do_order(db):
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
        @self.env.with_transaction()
        def do_remove(db):
            ticket = model.Ticket(self.env, number, db=db)
            ticket.delete()
        printout(_('Ticket #%(num)s and all associated data removed.',
                   num=number))
