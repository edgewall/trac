.. _upgradeinstructions:

Upgrade Instructions
====================

.. _instructions:

Instructions
------------

There are seven recommended steps for upgrading to a newer version of
Trac:

.. _a1.checkyourplugins:

1. Check your plugins
~~~~~~~~~~~~~~~~~~~~~

Check whether your plugins are compatible with the version of Trac that
you are upgrading to. Obsolete plugins listed in the `version specific
steps <#versionspecificsteps>`__ below should be uninstalled or
disabled.

If you are upgrading to a minor release, plugin compatibility is usually
not a concern because the Trac API is normally unchanged.

If your plugins are installed from
`trac-hacks.org <https://trac-hacks.org>`__ you can check compatibility
by looking for a tag on the project page corresponding to a major
release (e.g. ``1.4``). If you are unsure, you'll want to contact the
plugin author or ask on the
`MailingList <https://trac.edgewall.org/intertrac/MailingList>`__.

If you are running several Trac plugins it is good to test the upgrade
and plugin functionality in a staging instance of your site before
upgrading your production instance. Remember, plugin authors are
responsible for Trac version compatibility and plugins can interact in
unexpected ways. Your Trac instance may have a unique combination of
plugins and therefore it's advised that you do some verification testing
when making any changes to your site.

.. _a2.bringyourserveroff-line:

2. Bring your server off-line
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is not a good idea to update a running server: the server processes
may have parts of the current packages cached in memory, and updating
the code will likely trigger `internal errors <#zipimporterror>`__.

Although a database backup will be implicitly created by default when
upgrading the environment, it is always a good idea to perform a full
backup of the environment using the
`hotcopy <https://trac.edgewall.org/wiki/TracBackup>`__ command before
beginning. You may also wish to create a full backup of your server.

.. _updatethetraccode:

3. Update Trac and dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The packages are available through several channels, as described in
`TracDownload <https://trac.edgewall.org/intertrac/TracDownload>`__. If
your Trac instance was installed through an operating system package
manager, proceed with the standard steps that are appropriate for your
operating system package manager. If it was installed through a Windows
installer, uninstall the old Trac package before installing new Trac
package.

If you are managing your Trac installation using command line tools,
``pip`` is the preferred tool to upgrade a Trac instance because it will
uninstall the old version. The following command will upgrade your Trac
installation using the package published to
`PyPI <https://pypi.python.org/pypi/Trac>`__.

.. container:: wiki-code

   .. container:: code

      ::

         $ pip install --upgrade Trac

The upgrade command will give you the latest release of Trac. If instead
you wish to upgrade to a different version, such as a minor release of
Trac when there is a newer major release available, then specify the
Trac version in the ``pip`` command.

.. container:: wiki-code

   .. container:: code

      ::

         $ pip install --upgrade Trac==1.4.1

You should also upgrade dependencies so they are compliant with the
`required
versions <https://trac.edgewall.org/wiki/TracInstall#Dependencies>`__.

.. _upgradethetracenvironment:

4. Upgrade the Trac Environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Environment upgrades are not necessary for minor version releases unless
otherwise noted.

On starting your web server after upgrading Trac, a message will be
displayed for projects that need to be upgraded and the projects will
not be accessible until the upgrade is run.

The upgrade is run using a
`trac-admin <https://trac.edgewall.org/wiki/TracAdmin>`__ command:

.. container:: wiki-code

   .. container:: code

      ::

         $ trac-admin /path/to/projenv upgrade

This command will not have any effect if the environment is already
up-to-date.

It is recommended that you set the
`log_level <https://trac.edgewall.org/wiki/TracIni#logging-log_level-option>`__
to ``INFO`` before running the upgrade. The additional information in
the logs can be helpful in case something unexpected occurs during the
upgrade.

Note that a backup of your database will be performed automatically
prior to the upgrade. The backup is saved in the location specified by
`backup_dir <https://trac.edgewall.org/wiki/TracIni#trac-backup_dir-option>`__.

.. _updatethetracdocumentation:

5. Update the Trac Documentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, every `Trac
environment <https://trac.edgewall.org/wiki/TracEnvironment>`__ includes
a copy of the Trac documentation for the installed version. To keep the
documentation in sync with the installed version of Trac, upgrade the
documentation:

.. container:: wiki-code

   .. container:: code

      ::

         $ trac-admin /path/to/projenv wiki upgrade

Note that this procedure will leave your ``WikiStart``, ``InterMapTxt``
and ``SandBox`` pages unaltered. Local changes to other pages that are
distributed with Trac will be overwritten, however these pages are
read-only by default for Environments created in Trac 1.3.3 and later.

.. _a6.refreshstaticresources:

6. Refresh static resources
~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you have configured your web server to serve static resources
directly (accessed using the ``/chrome/`` URL) then you will need to
refresh them using the `deploy
command <https://trac.edgewall.org/wiki/TracInstall#MappingStaticResources>`__.
The ``deploy`` command will extract static resources and CGI scripts
(``trac.wsgi``, etc) from the new Trac version and plugins into
``/deploy/path``.

.. container:: wiki-code

   .. container:: code

      ::

         $ trac-admin /path/to/env deploy /deploy/path

Before refreshing, it is recommended that you remove the directory in
which your static resources are deployed. The directory location depends
on the choice you made during installation. This cleanup is not
mandatory, but makes it easier to troubleshoot issues as your
installation is uncluttered by unused assets from a previous release. As
usual, make a backup before deleting the directory.

.. container:: wikipage

   **Note:** Some web browsers (IE, Opera) cache CSS and JavaScript
   files, so you should instruct your users to manually erase the
   contents of their browser's cache. A forced refreshed (SHIFT + <F5>)
   should be sufficient.

.. _versionspecificsteps:

7. Steps specific to a given Trac version
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. _to1.5:

Upgrading from Trac 1.4 to 1.5
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _python2.7nolongersupported:

Python 2.7 no longer supported
''''''''''''''''''''''''''''''

Upgrade Python to 3.5 or later.

.. _to1.4:

Upgrading from Trac 1.2 to 1.4
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _python2.6nolongersupported:

Python 2.6 no longer supported
''''''''''''''''''''''''''''''

Upgrade Python to 2.7, but not 3.0 or greater.

.. _mysql-pythonnolongersupported:

MySQL-python no longer supported
''''''''''''''''''''''''''''''''

`PyMySQL <https://pypi.python.org/pypi/PyMySQL>`__ is the supported
MySQL database library, support for
`MySQL-python <https://pypi.python.org/pypi/MySQL-python>`__ has been
removed.

.. _obsoleteplugins:

Obsolete Plugins
''''''''''''''''

Trac has added functionality equivalent to the following plugins:

-  `DynamicVariablesPlugin <https://trac-hacks.org/wiki/DynamicVariablesPlugin>`__:
   dynamic variables are autocompleted
-  `NavAddPlugin <https://trac-hacks.org/wiki/NavAddPlugin>`__: see
   `TracNavigation <https://trac.edgewall.org/wiki/TracNavigation>`__
-  `FlexibleAssignToPlugin <https://trac-hacks.org/wiki/FlexibleAssignToPlugin>`__:
   subclass ``ConfigurableTicketWorkflow`` and override
   ``get_allowed_owners``
-  `TracMigratePlugin <https://trac-hacks.org/wiki/TracMigratePlugin>`__:
   Use the ``trac-admin`` `convert_db
   command <https://trac.edgewall.org/wiki/TracAdmin#ChangingDatabaseBackend>`__

The plugins should be removed when upgrading Trac to 1.4.

.. _jinja2isthenewtemplateengine:

Jinja2 is the new template engine
'''''''''''''''''''''''''''''''''

Content is now generated by using the Jinja2 template engine. You should
verify that your plugins are compatible with this change.

If you customized the Trac templates, or the ``site.html`` template,
you'll need to adapt that as well. (TODO: expand...) See
`#CustomizedTemplates <#customizedtemplates>`__. Email `notification
templates <https://trac.edgewall.org/wiki/TracNotification#CustomizingContent>`__
also need to be adapted.

.. _newpermissionpoliciesforwikiandticketrealms:

New permission policies for Wiki and Ticket realms
''''''''''''''''''''''''''''''''''''''''''''''''''

Since 1.3.2 there are new permission policies for the ticket and wiki
systems. ``DefaultTicketPolicy`` allows an authenticated user with
``TICKET_APPEND`` or ``TICKET_CHPROP`` to modify the description of a
ticket they reported. It also implements the pre-1.3.2 behavior of
allowing users to edit their own ticket comments.
`ReadonlyWikiPolicy <https://trac.edgewall.org/wiki/TracUpgrade#Newpermissionspolicyforread-onlywikipages>`__,
added in 1.1.2, is renamed to ``DefaultWikiPolicy``. The new permission
policies can be easily replaced with alternate implementations if the
default behavior is not desired.

If ``[trac] permission_policy`` has the default value
``ReadonlyWikiPolicy, DefaultPermissionPolicy, LegacyAttachmentPolicy``,
then ``DefaultWikiPolicy, DefaultTicketPolicy`` should be automatically
appended to the list when upgrading the environment:

.. container:: wiki-code

   .. container:: code

      ::

         [trac]
         permission_policies = DefaultWikiPolicy,
          DefaultTicketPolicy,
          DefaultPermissionPolicy,
          LegacyAttachmentPolicy

If other permission policies are enabled, ``trac.ini`` will need to be
edited to add ``DefaultWikiPolicy, DefaultTicketPolicy`` to
``permission_policies``. See
`TracFineGrainedPermissions <https://trac.edgewall.org/wiki/TracFineGrainedPermissions#DefaultWikiPolicyandDefaultTicketPolicy>`__
for additional details on the proper ordering.

.. _enum-description-field:

Description field added to ticket enums
'''''''''''''''''''''''''''''''''''''''

The ticket enums now have a *description* field. An *ambiguous column
name* error may be seen for reports that reference the ``description``
column of another table and join the ``enum`` table with that table
(e.g. ``ticket``, ``component``). The reports {1}, {2}, {3}, {4}, {5},
{7}, and {8} are modified by an upgrade step to fix the issue, but the
modification may not succeed if the default reports have been modified,
in which case ``upgrade`` will output a message to the terminal
instructing the user to modify the reports. User-created reports may
also need to be modified.

Reports that display the error need to be modified to prefix the
``description`` column with the appropriate table name or alias. For
example, if the ``ticket`` table is aliased as ``t`` (``ticket t`` or
``ticket AS t``), replace ``description`` with ``t.description`` if the
report should use the ticket's ``description`` column.

.. _removedrepostypeandrepospathargumentsfromtrac-admininitenvcommand:

Removed ``<repostype>`` and ``<repospath>`` arguments from ``trac-admin`` ``initenv`` command
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

The `TracAdmin <https://trac.edgewall.org/wiki/TracAdmin>`__ ``initenv``
command allowed the default repository to be specified using the third
and fourth positional arguments of ``initenv``:

.. container:: wiki-code

   .. container:: code

      ::

         initenv [<projectname> <db> [<repostype> <repospath>]]

The arguments were an artifact of Trac < 0.12, which only supported a
single repository. Trac 0.12 and later supports multiple repositories,
which can be specified at the time of environment creation using the
``--inherit`` and ``--config`` arguments. See the `initenv
documentation <https://trac.edgewall.org/wiki/TracEnvironment#SourceCodeRepository>`__
for details on specifying source code repositories.

.. _to1.2:

Upgrading from Trac 1.0 to 1.2
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _python2.5nolongersupported:

Python 2.5 no longer supported
''''''''''''''''''''''''''''''

Upgrade Python to at least 2.6 or 2.7, but not 3.0 or greater.

.. _obsoleteplugins1:

Obsolete Plugins
''''''''''''''''

Trac has added functionality equivalent to the following plugins:

-  `AdminEnumListPlugin <https://trac-hacks.org/wiki/AdminEnumListPlugin>`__
-  `AttachmentNotifyPlugin <https://trac-hacks.org/wiki/AttachmentNotifyPlugin>`__:
   attachment notifications are sent in Trac 1.0.3 and later
-  `DateFieldPlugin <https://trac-hacks.org/wiki/DateFieldPlugin>`__:
   see the **time** `custom field
   type <https://trac.edgewall.org/wiki/TracTicketsCustomFields#AvailableFieldTypesandOptions>`__
-  `FlexibleReporterNotificationPlugin <https://trac-hacks.org/wiki/FlexibleReporterNotificationPlugin>`__:
   `custom
   subscribers <https://trac.edgewall.org/intertrac/CookBook/Notification/Subscriptions>`__
   can be implemented in the new extensible notification system
-  `GroupBasedRedirectionPlugin <https://trac-hacks.org/wiki/GroupBasedRedirectionPlugin>`__:
   the default handler can set as a user preference
-  `GroupingAssignToPlugin <https://trac-hacks.org/wiki/GroupingAssignToPlugin>`__:
   groups and permissions can be used in the
   `set_owner <https://trac.edgewall.org/wiki/TracWorkflow#BasicTicketWorkflowCustomization>`__
   workflow attribute
-  `LinenoMacro <https://trac-hacks.org/wiki/LinenoMacro>`__: see
   `WikiProcessors#AvailableProcessors <https://trac.edgewall.org/wiki/WikiProcessors#AvailableProcessors>`__
-  `NeverNotifyUpdaterPlugin <https://trac-hacks.org/wiki/NeverNotifyUpdaterPlugin>`__:
   see `notification
   subscribers <https://trac.edgewall.org/wiki/TracNotification#notification-subscriber-section>`__
-  `QueryUiAssistPlugin <https://trac-hacks.org/wiki/QueryUiAssistPlugin>`__:
   see
   `TracQuery#Filters <https://trac.edgewall.org/wiki/TracQuery#Filters>`__.
-  `TicketCreationStatusPlugin <https://trac-hacks.org/wiki/TicketCreationStatusPlugin>`__:
   see `#NewWorkflowActions <#newworkflowactions>`__

The plugins should be removed when upgrading Trac to 1.2.

.. _newworkflowactions:

New workflow actions
''''''''''''''''''''

The ticket creation step is controlled with a workflow action. The
default workflow has ``create`` and ``create_and_assign`` actions. The
``create`` action will always be added when upgrading the database. The
``create_and_assign`` action will be added if the workflow has an
*assigned* state. You may want to edit your workflow after upgrading the
database to customize the actions available on the *New Ticket* page.

.. _newpermissionspolicyforread-onlywikipages:

New permissions policy for read-only wiki pages
'''''''''''''''''''''''''''''''''''''''''''''''

Since 1.1.2 the read-only attribute of wiki pages is enabled and
enforced only when ``ReadonlyWikiPolicy`` is in the list of active
permission policies. If ``[trac] permission_policy`` has the default
value ``DefaultPermissionPolicy, LegacyAttachmentPolicy``, then
``ReadonlyWikiPolicy`` should be automatically appended to the list when
upgrading the environment:

.. container:: wiki-code

   .. container:: code

      ::

         [trac]
         permission_policies = ReadonlyWikiPolicy,
          DefaultPermissionPolicy,
          LegacyAttachmentPolicy

If other permission policies are enabled, ``trac.ini`` will need to have
``ReadonlyWikiPolicy`` appended to the list of active
``permission_policies``. See
`TracFineGrainedPermissions#ReadonlyWikiPolicy <https://trac.edgewall.org/wiki/TracFineGrainedPermissions#ReadonlyWikiPolicy>`__
for additional details on the proper ordering.

.. _navigationorderingmoved:

Navigation Ordering Moved
'''''''''''''''''''''''''

The mainnav and metanav configuration ordering have been moved from
``[trac]`` ``mainnav`` and ``[trac]`` ``metanav`` to the ``[mainnav]``
and ``[metanav]`` sections. The ordering is now specified using the
``order`` attribute as described in
`TracNavigation <https://trac.edgewall.org/wiki/TracNavigation#nav-order>`__.

The new configuration values will be written to trac.ini on upgrade,
preserving the navigation order for the environment. You may need to
edit trac.ini if you use a shared `global
configuration <https://trac.edgewall.org/wiki/TracIni#GlobalConfiguration>`__.
For example, if you wish to specify the navigation ordering for several
environments in ``global.ini``, you'll need to add the ``[mainnav]`` and
``[metanav]`` sections in that file and delete those sections from each
environment's trac.ini.

.. _to1.0:

Upgrading from Trac 0.12 to Trac 1.0
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _python2.4nolongersupported:

Python 2.4 no longer supported
''''''''''''''''''''''''''''''

Upgrade Python to at least 2.5, but not 3.0.

.. _obsoleteplugins2:

Obsolete Plugins
''''''''''''''''

Trac has added functionality equivalent to the following plugins:

-  `AnchorMacro <https://trac-hacks.org/wiki/AnchorMacro>`__
-  `BatchModifyPlugin <https://trac-hacks.org/wiki/BatchModifyPlugin>`__
-  `GitPlugin <https://trac-hacks.org/wiki/GitPlugin>`__
-  `OverrideEditPlugin <https://trac-hacks.org/wiki/OverrideEditPlugin>`__
-  `ProgressMeterMacro <https://trac-hacks.org/wiki/ProgressMeterMacro>`__

The plugins should be removed when upgrading Trac to 1.0.

.. _subversioncomponentsnotenabledbydefaultfornewinstallations:

Subversion components not enabled by default for new installations
''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

The Trac components for Subversion support are no longer enabled by
default. To enable the svn support, you need to make sure the
``tracopt.versioncontrol.svn`` components are enabled, for example by
setting the following in the
`TracIni <https://trac.edgewall.org/wiki/TracIni>`__:

.. container:: wiki-code

   .. container:: code

      ::

         [components]
         tracopt.versioncontrol.svn.* = enabled

The upgrade procedure should take care of this and change the
`TracIni <https://trac.edgewall.org/wiki/TracIni>`__ appropriately,
unless you already had the svn components explicitly disabled.

.. _attachmentsmigrated:

Attachments migrated to new location
''''''''''''''''''''''''''''''''''''

Another step in the automatic upgrade will change the way the
attachments are stored. There have been reports that the attachment
migration `sometimes fails <#attachmentsnotmigrated>`__, so it's extra
important that you `backup your
environment <https://trac.edgewall.org/wiki/TracBackup>`__.

In case the ``attachments`` directory contains some files which are
*not* attachments, the last step of the migration to the new layout will
not be completed: the deletion of the now unused ``attachments``
directory can't be done if there are still files and folders in it. You
may ignore this error, but better to move them elsewhere and remove the
``attachments`` directory manually. The attachments themselves are now
all located in your environment below the ``files/attachments``
directory.

.. _behaviorofticketdefault_ownerchanged:

Behavior of ``[ticket] default_owner`` changed
''''''''''''''''''''''''''''''''''''''''''''''

Prior to 1.0, the owner field of new tickets always defaulted to
``[ticket] default_owner`` when the value was not empty. If the value
was empty, the owner field defaulted to to the Component's owner. In 1.0
and later, the ``default_owner`` must be set to ``< default >`` to make
new tickets default to the Component's owner. This change allows the
``default_owner`` to be set to an empty value if no default owner is
desired.

.. _behaviorof-workflowtransition:

Behavior of ``* -> *`` workflow transition
''''''''''''''''''''''''''''''''''''''''''

The workflow transition ``* -> *`` must have the operation
``leave_status``. Due to a defect in Trac < 1.0.18 ``leave_status`` was
not required, so it may be necessary to add the operation when
upgrading. The action will not display for a ``* -> *`` transition if
the action does not have the ``leave_status`` operation.

.. _olderversions:

Upgrading from older versions of Trac
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For upgrades from versions older than Trac 0.12, refer first to
`TracUpgrade for
0.12 <https://trac.edgewall.org/intertrac/wiki%3A0.12/TracUpgrade%23SpecificVersions>`__.

For upgrades from versions older than Trac 0.10, refer first to
`TracUpgrade for
0.10 <https://trac.edgewall.org/intertrac/wiki%3A0.10/TracUpgrade%23SpecificVersions>`__.

.. _knownissues:

Known Issues
------------

.. _customizedtemplates:

Customized Templates
~~~~~~~~~~~~~~~~~~~~

Trac supports customization of its templates by placing copies of the
templates in the ``<env>/templates`` folder of your
`environment <https://trac.edgewall.org/wiki/TracEnvironment>`__ or in a
common location specified in the
`inherit.templates_dir <https://trac.edgewall.org/wiki/TracIni#GlobalConfiguration>`__
configuration setting. If you choose to customize the templates, be
aware that you will need to repeat your changes on a copy of the new
templates when you upgrade to a new release of Trac (even a minor one),
as the templates will evolve. So keep a diff around.

The preferred way to perform
`TracInterfaceCustomization <https://trac.edgewall.org/wiki/TracInterfaceCustomization>`__
is a custom plugin doing client-side JavaScript transformation of the
generated output, as this is more robust in case of changes: we usually
won't modify an element ``id`` or change its CSS ``class``, and if we
have to do so, this will be documented in the
`TracDev/ApiChanges <https://trac.edgewall.org/intertrac/TracDev/ApiChanges>`__
pages.

.. _zipimporterror:

ZipImportError
~~~~~~~~~~~~~~

Due to internal caching of zipped packages, whenever the content of the
packages change on disk, the in-memory zip index will no longer match
and you'll get irrecoverable ZipImportError errors. Better to anticipate
and bring your server down for maintenance before upgrading. See
`#7014 <https://trac.edgewall.org/intertrac/%237014>`__ for details.

.. _wikiupgrade:

Wiki Upgrade
~~~~~~~~~~~~

``trac-admin`` will not delete or remove default wiki pages that were
present in a previous version but are no longer in the new version.

.. _parentdir:

Parent dir
~~~~~~~~~~

If you use a Trac parent env configuration and one of the plugins in one
child does not work, none of the children will work.

.. _attachmentsnotmigrated:

Attachments not migrated
~~~~~~~~~~~~~~~~~~~~~~~~

There have been reports that attachments are not
`migrated <#attachmentsmigrated>`__ when upgrading to Trac 1.0 or later.
The cause of the issue has not yet been found. If you encounter this
issue, see `the
FAQ <https://trac.edgewall.org/wiki/TracFaq#Q:Attachmentsaremissingafterupgrade>`__
for a workaround and please report your findings to
`#11370 <https://trac.edgewall.org/intertrac/%2311370>`__.

.. _relatedtopics:

Related topics
--------------

.. _upgradingpython:

Upgrading Python
~~~~~~~~~~~~~~~~

Upgrading Python to a newer version will require reinstallation of
Python packages: Trac itself of course, but also
`dependencies <https://trac.edgewall.org/wiki/TracInstall#Dependencies>`__.
If you are using Subversion, you'll need to upgrade the `Python bindings
for SVN <https://trac.edgewall.org/intertrac/TracSubversion>`__.

--------------

See also: `TracGuide <https://trac.edgewall.org/wiki/TracGuide>`__,
`TracInstall <https://trac.edgewall.org/wiki/TracInstall>`__

