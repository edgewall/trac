# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2019 Edgewall Software
# Copyright (C) 2003-2016 Jonas Borgström <jonas@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

from trac.core import Interface


class ISystemInfoProvider(Interface):
    """Provider of system information, displayed in the "About Trac"
    page and in internal error reports.
    """
    def get_system_info():
        """Yield a sequence of `(name, version)` tuples describing the
        name and version information of external packages used by a
        component.
        """


class IEnvironmentSetupParticipant(Interface):
    """Extension point interface for components that need to participate in
    the creation and upgrading of Trac environments, for example to create
    additional database tables.

    Please note that `IEnvironmentSetupParticipant` instances are called in
    arbitrary order. If your upgrades must be ordered consistently, please
    implement the ordering in a single `IEnvironmentSetupParticipant`. See
    the database upgrade infrastructure in Trac core for an example.
    """

    def environment_created():
        """Called when a new Trac environment is created."""

    def environment_needs_upgrade():
        """Called when Trac checks whether the environment needs to be
        upgraded.

        Should return `True` if this participant needs an upgrade to
        be performed, `False` otherwise.
        """

    def upgrade_environment():
        """Actually perform an environment upgrade.

        Implementations of this method don't need to commit any
        database transactions. This is done implicitly for each
        participant if the upgrade succeeds without an error being
        raised.

        However, if the `upgrade_environment` consists of small,
        restartable, steps of upgrade, it can decide to commit on its
        own after each successful step.
        """
