Upgrade Instructions
====================


Instructions
------------

There are seven recommended steps for upgrading to a newer version of
Trac:


1. Check your plugins
~~~~~~~~~~~~~~~~~~~~~

Check whether your plugins are compatible with the version of Trac
that you are upgrading to. Obsolete plugins listed in the `version
specific steps`_ below should be uninstalled or disabled.

If you are upgrading to a minor release, plugin compatibility is
usually not a concern because the Trac API rarely changes, and major
features are usually not introduced, for minor releases.

If your plugins are installed from `trac-hacks.org`_ you can check
compatibility by looking for a tag on the project page corresponding
to a major release (e.g. `1.2`). If you are unsure, you'll want to
contact the plugin author or ask on the `MailingList`_.

If you are running several Trac plugins it is good to test the upgrade
and plugin functionality in a staging instance of your site before
upgrading your production instance. Remember, plugin authors are
responsible for Trac version compatibility and plugins can interact in
unexpected ways. Your Trac instance may have a unique combination of
plugins and therefore it's advised that you do some verification
testing when making any changes to your site.


2. Bring your server off-line
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is not a good idea to update a running server: the server processes
may have parts of the current packages cached in memory, and updating
the code will likely trigger `internal errors`_.

Although a database backup will be implicitly created by default when
upgrading the environment, it is always a good idea to perform a full
backup of the environment using the `hotcopy`_ command before
beginning. You may also wish to create a full backup of your server.


3. Update Trac and dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The packages are available through several channels, as described in
`TracDownload`_. If your Trac instance was installed through an
operating system package manager or an installer on Windows, proceed
with the standard steps that are appropriate for your operating
system.

If you are managing your Trac installation using command line tools,
`pip` is the preferred tool to upgrade a Trac instance because it will
uninstall the old version. The following command will upgrade your
Trac installation using the package published to `PyPI`_.


::

    $ pip install --upgrade Trac


The upgrade command will give you the latest release of Trac. If
instead you wish to upgrade to a different version, such as a minor
release of Trac when there is a newer major release available, then
specify the Trac version in the `pip` command.


::

    $ pip install --upgrade Trac==1.2.1


You should also upgrade dependencies so they are compliant with the
`required versions`_.


4. Upgrade the Trac Environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Environment upgrades are not necessary for minor version releases
unless otherwise noted.

On starting your web server after upgrading Trac, a message will be
displayed for projects that need to be upgraded and the projects will
not be accessible until the upgrade is run.

The upgrade is run using a `trac-admin`_ command:


::

    $ trac-admin /path/to/projenv upgrade


This command will not have any effect if the environment is already
up-to-date.

It is recommended that you set the `log_level`_ to `INFO` before
running the upgrade. The additional information in the logs can be
helpful in case something unexpected occurs during the upgrade.

Note that a backup of your database will be performed automatically
prior to the upgrade. The backup is saved in the location specified by
`backup_dir`_.


5. Update the Trac Documentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, every `Trac environment`_ includes a copy of the Trac
documentation for the installed version. To keep the documentation in
sync with the installed version of Trac, upgrade the documentation:


::

    $ trac-admin /path/to/projenv wiki upgrade


Note that this procedure will leave your `WikiStart`, `InterMapTxt`
and `SandBox` pages unaltered. Local changes to other pages that are
distributed with Trac will be overwritten, however these pages are
read-only by default for Environments created in Trac 1.3.3 and later.


6. Refresh static resources
~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you have configured your web server to serve static resources
directly (accessed using the `/chrome/` URL) then you will need to
refresh them using the `deploy command`_. The `deploy` command will
extract static resources and CGI scripts ( `trac.wsgi`, etc) from the
new Trac version and plugins into `/deploy/path`.


::

    $ trac-admin /path/to/env deploy /deploy/path


Before refreshing, it is recommended that you remove the directory in
which your static resources are deployed. The directory location
depends on the choice you made during installation. This cleanup is
not mandatory, but makes it easier to troubleshoot issues as your
installation is uncluttered by unused assets from a previous release.
As usual, make a backup before deleting the directory.

Note: Some web browsers (IE, Opera) cache CSS and JavaScript files, so
you should instruct your users to manually erase the contents of their
browser's cache. A forced refreshed (SHIFT + <F5>) should be
sufficient.


7. Steps specific to a given Trac version
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


Upgrading from Trac 1.2 to 1.4
``````````````````````````````


Python 2.6 no longer supported
++++++++++++++++++++++++++++++

Upgrade Python to 2.7, but not 3.0 or greater.


MySQL-python no longer supported
++++++++++++++++++++++++++++++++

`PyMySQL`_ is the supported MySQL database library, support for
`MySQL-python`_ has been removed.


Obsolete Plugins
++++++++++++++++

Trac has added functionality equivalent to the following plugins:


+ `DynamicVariablesPlugin`_: dynamic variables are autocompleted
+ `NavAddPlugin`_: see `TracNavigation`_
+ `FlexibleAssignToPlugin`_: subclass `ConfigurableTicketWorkflow` and
  override `get_allowed_owners`
+ `TracMigratePlugin`_: Use the `trac-admin` `convert_db command`_


The plugins should be removed when upgrading Trac to 1.4.


Jinja2 is the new template engine
+++++++++++++++++++++++++++++++++

Content is now generated by using the Jinja2 template engine. You may
want to verify that your plugins are compatible with this change.
(TODO: expand...)

If you customized the Trac templates, or the `site.html` template,
you'll need to adapt that as well. (TODO: expand...) See
`#CustomizedTemplates`_


New permission policies for Wiki and Ticket realms
++++++++++++++++++++++++++++++++++++++++++++++++++

Since 1.3.2 there are new permission policies for the ticket and wiki
systems. `DefaultTicketPolicy` allows an authenticated users with
`TICKET_APPEND` or `TICKET_CHPROP` to modify the description of a
ticket they reported. It also implements the pre-1.3.2 behavior of
allowing users to edit their own ticket comments.
`ReadonlyWikiPolicy`_, added in 1.1.2, is renamed to
`DefaultWikiPolicy`. The new permission policies can be easily
replaced with alternate implementations if the default behavior is not
desired.

If `[trac] permission_policy` has the default value
`ReadonlyWikiPolicy, DefaultPermissionPolicy, LegacyAttachmentPolicy`,
then `DefaultWikiPolicy, DefaultTicketPolicy` should be automatically
appended to the list when upgrading the environment:


::

    [trac]
    permission_policies = DefaultWikiPolicy,
     DefaultTicketPolicy,
     DefaultPermissionPolicy,
     LegacyAttachmentPolicy


If other permission policies are enabled, `trac.ini` will need to be
edited to add `DefaultWikiPolicy, DefaultTicketPolicy` to
`permission_policies`. See `TracFineGrainedPermissions`_ for
additional details on the proper ordering.


Description field added to ticket enums
+++++++++++++++++++++++++++++++++++++++

The ticket enums now have a *description* field. An *ambiguous column
name* error may be seen for reports that reference the `description`
column of another table and join the `enum` table with that table
(e.g. `ticket`, `component`). The reports {1}, {2}, {3}, {4}, {5},
{7}, and {8} are modified by an upgrade step to fix the issue, but the
modification may not succeed if the default reports have been
modified, in which case `upgrade` will output a message to the
terminal instructing the user to modify the reports. User-created
reports may also need to be modified.

Reports that display the error need to be modified to prefix the
`description` column with the appropriate table name or alias. For
example, if the `ticket` table is aliased as `t` ( `ticket t` or
`ticket AS t`), replace `description` with `t.description` if the
report should use the ticket's `description` column.


Removed `<repostype>` and `<repospath>` arguments from `TracAdmin`_
`initenv` command
+++++++++++++++++

The `TracAdmin`_ `initenv` command allowed the default repository to
be specified using the third and fourth positional arguments of
`initenv`:

::

    initenv [<projectname> <db> [<repostype> <repospath>]]


The arguments were an artifact of Trac < 0.12, which only supported a
single repository. Trac 0.12 and later supports multiple repositories,
which can be specified at the time of environment creation using the
`--inherit` and `--config` arguments. See the `initenv documentation`_
for details on specifying source code repositories.


Upgrading from Trac 1.0 to 1.2
``````````````````````````````


Python 2.5 no longer supported
++++++++++++++++++++++++++++++

Upgrade Python to at least 2.6 or 2.7, but not 3.0 or greater.


Obsolete Plugins
++++++++++++++++

Trac has added functionality equivalent to the following plugins:


+ `AdminEnumListPlugin`_
+ `AttachmentNotifyPlugin`_: attachment notifications are sent in Trac
  1.0.3 and later
+ `DateFieldPlugin`_: see the time `custom field type`_
+ `FlexibleReporterNotificationPlugin`_: `custom subscribers`_ can be
  implemented in the new extensible notification system
+ `GroupBasedRedirectionPlugin`_: the default handler can set as a
  user preference
+ `GroupingAssignToPlugin`_: groups and permissions can be used in the
  `set_owner`_ workflow attribute
+ `LinenoMacro`_: see `WikiProcessors#AvailableProcessors`_
+ `NeverNotifyUpdaterPlugin`_: see `notification subscribers`_
+ `QueryUiAssistPlugin`_: see `TracQuery#Filters`_.
+ `TicketCreationStatusPlugin`_: see `#NewWorkflowActions`_


The plugins should be removed when upgrading Trac to 1.2.


New workflow actions
++++++++++++++++++++

The ticket creation step is controlled with a workflow action. The
default workflow has `create` and `create_and_assign` actions. The
`create` action will always be added when upgrading the database. The
`create_and_assign` action will be added if the workflow has an
*assigned* state. You may want to edit your workflow after upgrading
the database to customize the actions available on the *New Ticket*
page.


New permissions policy for read-only wiki pages
+++++++++++++++++++++++++++++++++++++++++++++++

Since 1.1.2 the read-only attribute of wiki pages is enabled and
enforced only when `ReadonlyWikiPolicy` is in the list of active
permission policies. If `[trac] permission_policy` has the default
value `DefaultPermissionPolicy, LegacyAttachmentPolicy`, then
`ReadonlyWikiPolicy` should be automatically appended to the list when
upgrading the environment:


::

    [trac]
    permission_policies = ReadonlyWikiPolicy,
     DefaultPermissionPolicy,
     LegacyAttachmentPolicy


If other permission policies are enabled, `trac.ini` will need to have
`ReadonlyWikiPolicy` appended to the list of active
`permission_policies`. See
`TracFineGrainedPermissions#ReadonlyWikiPolicy`_ for additional
details on the proper ordering.


Upgrading from Trac 0.12 to Trac 1.0
````````````````````````````````````


Python 2.4 no longer supported
++++++++++++++++++++++++++++++

Upgrade Python to at least 2.5, but not 3.0.


Obsolete Plugins
++++++++++++++++

Trac has added functionality equivalent to the following plugins:


+ `AnchorMacro`_
+ `BatchModifyPlugin`_
+ `GitPlugin`_
+ `OverrideEditPlugin`_
+ `ProgressMeterMacro`_


The plugins should be removed when upgrading Trac to 1.0.


Subversion components not enabled by default for new installations
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

The Trac components for Subversion support are no longer enabled by
default. To enable the svn support, you need to make sure the
`tracopt.versioncontrol.svn` components are enabled, for example by
setting the following in the `TracIni`_:


::

    [components]
    tracopt.versioncontrol.svn.* = enabled


The upgrade procedure should take care of this and change the
`TracIni`_ appropriately, unless you already had the svn components
explicitly disabled.


Attachments migrated to new location
++++++++++++++++++++++++++++++++++++

Another step in the automatic upgrade will change the way the
attachments are stored. There have been reports that the attachment
migration `sometimes fails`_, so it's extra important that you `backup
your environment`_.

In case the `attachments` directory contains some files which are
*not* attachments, the last step of the migration to the new layout
will not be completed: the deletion of the now unused `attachments`
directory can't be done if there are still files and folders in it.
You may ignore this error, but better to move them elsewhere and
remove the `attachments` directory manually. The attachments
themselves are now all located in your environment below the
`files/attachments` directory.


Behavior of `[ticket] default_owner` changed
++++++++++++++++++++++++++++++++++++++++++++

Prior to 1.0, the owner field of new tickets always defaulted to
`[ticket] default_owner` when the value was not empty. If the value
was empty, the owner field defaulted to to the Component's owner. In
1.0 and later, the `default_owner` must be set to `< default >` to
make new tickets default to the Component's owner. This change allows
the `default_owner` to be set to an empty value if no default owner is
desired.


Upgrading from older versions of Trac
`````````````````````````````````````

For upgrades from versions older than Trac 0.12, refer first to
`TracUpgrade for 0.12`_.

For upgrades from versions older than Trac 0.10, refer first to
`TracUpgrade for 0.10`_.


Known Issues
------------


Customized Templates
~~~~~~~~~~~~~~~~~~~~

Trac supports customization of its templates by placing copies of the
templates in the `<env>/templates` folder of your `environment`_ or in
a common location specified in the `inherit.templates_dir`_
configuration setting. If you choose to customize the templates, be
aware that you will need to repeat your changes on a copy of the new
templates when you upgrade to a new release of Trac (even a minor
one), as the templates will evolve. So keep a diff around.

The preferred way to perform `TracInterfaceCustomization`_ is a custom
plugin doing client-side JavaScript transformation of the generated
output, as this is more robust in case of changes: we usually won't
modify an element `id` or change its CSS `class`, and if we have to do
so, this will be documented in the `TracDev/ApiChanges`_ pages.


ZipImportError
~~~~~~~~~~~~~~

Due to internal caching of zipped packages, whenever the content of
the packages change on disk, the in-memory zip index will no longer
match and you'll get irrecoverable ZipImportError errors. Better to
anticipate and bring your server down for maintenance before
upgrading. See `#7014`_ for details.


Wiki Upgrade
~~~~~~~~~~~~

`trac-admin` will not delete or remove default wiki pages that were
present in a previous version but are no longer in the new version.


Parent dir
~~~~~~~~~~

If you use a Trac parent env configuration and one of the plugins in
one child does not work, none of the children will work.


Attachments not migrated
~~~~~~~~~~~~~~~~~~~~~~~~

There have been reports that attachments are not `migrated`_ when
upgrading to Trac 1.0 or later. The cause of the issue has not yet
been found. If you encounter this issue, see `the FAQ`_ for a
workaround and please report your findings to `#11370`_.


Related topics
--------------


Upgrading Python
~~~~~~~~~~~~~~~~

Upgrading Python to a newer version will require reinstallation of
Python packages: Trac itself of course, but also `dependencies`_. If
you are using Subversion, you'll need to upgrade the `Python bindings
for SVN`_.


See also: `TracGuide`_, `TracInstall`_

.. _#11370: https://trac.edgewall.org/intertrac/%2311370
.. _#7014: https://trac.edgewall.org/intertrac/%237014
.. _#CustomizedTemplates: https://trac.edgewall.org/wiki/TracUpgrade#CustomizedTemplates
.. _#NewWorkflowActions: https://trac.edgewall.org/wiki/TracUpgrade#NewWorkflowActions
.. _AdminEnumListPlugin: https://trac-hacks.org/wiki/AdminEnumListPlugin
.. _AnchorMacro: https://trac-hacks.org/wiki/AnchorMacro
.. _AttachmentNotifyPlugin: https://trac-hacks.org/wiki/AttachmentNotifyPlugin
.. _backup your environment: https://trac.edgewall.org/wiki/TracBackup
.. _backup_dir: https://trac.edgewall.org/wiki/TracIni#trac-backup_dir-option
.. _BatchModifyPlugin: https://trac-hacks.org/wiki/BatchModifyPlugin
.. _convert_db command: https://trac.edgewall.org/wiki/TracAdmin#ChangingDatabaseBackend
.. _custom field type: https://trac.edgewall.org/wiki/TracTicketsCustomFields#AvailableFieldTypesandOptions
.. _custom subscribers: https://trac.edgewall.org/intertrac/CookBook/Notification/Subscriptions
.. _DateFieldPlugin: https://trac-hacks.org/wiki/DateFieldPlugin
.. _dependencies: https://trac.edgewall.org/wiki/TracInstall#Dependencies
.. _deploy command: https://trac.edgewall.org/wiki/TracInstall#MappingStaticResources
.. _DynamicVariablesPlugin: https://trac-hacks.org/wiki/DynamicVariablesPlugin
.. _environment: https://trac.edgewall.org/wiki/TracEnvironment
.. _FlexibleAssignToPlugin: https://trac-hacks.org/wiki/FlexibleAssignToPlugin
.. _FlexibleReporterNotificationPlugin: https://trac-hacks.org/wiki/FlexibleReporterNotificationPlugin
.. _GitPlugin: https://trac-hacks.org/wiki/GitPlugin
.. _GroupBasedRedirectionPlugin: https://trac-hacks.org/wiki/GroupBasedRedirectionPlugin
.. _GroupingAssignToPlugin: https://trac-hacks.org/wiki/GroupingAssignToPlugin
.. _hotcopy: https://trac.edgewall.org/wiki/TracBackup
.. _inherit.templates_dir: https://trac.edgewall.org/wiki/TracIni#GlobalConfiguration
.. _initenv documentation: https://trac.edgewall.org/wiki/TracEnvironment#SourceCodeRepository
.. _internal errors: https://trac.edgewall.org/wiki/TracUpgrade#ZipImportError
.. _LinenoMacro: https://trac-hacks.org/wiki/LinenoMacro
.. _log_level: https://trac.edgewall.org/wiki/TracIni#logging-log_level-option
.. _MailingList: https://trac.edgewall.org/intertrac/MailingList
.. _migrated: https://trac.edgewall.org/wiki/TracUpgrade#AttachmentsMigrated
.. _MySQL-python: https://pypi.python.org/pypi/MySQL-python
.. _NavAddPlugin: https://trac-hacks.org/wiki/NavAddPlugin
.. _NeverNotifyUpdaterPlugin: https://trac-hacks.org/wiki/NeverNotifyUpdaterPlugin
.. _notification subscribers: https://trac.edgewall.org/wiki/TracNotification#notification-subscriber-section
.. _OverrideEditPlugin: https://trac-hacks.org/wiki/OverrideEditPlugin
.. _ProgressMeterMacro: https://trac-hacks.org/wiki/ProgressMeterMacro
.. _PyMySQL: https://pypi.python.org/pypi/PyMySQL
.. _PyPI: https://pypi.python.org/pypi/Trac
.. _Python bindings for SVN: https://trac.edgewall.org/intertrac/TracSubversion
.. _QueryUiAssistPlugin: https://trac-hacks.org/wiki/QueryUiAssistPlugin
.. _ReadonlyWikiPolicy: https://trac.edgewall.org/wiki/TracUpgrade#Newpermissionspolicyforread-onlywikipages
.. _required versions: https://trac.edgewall.org/wiki/TracInstall#Dependencies
.. _set_owner: https://trac.edgewall.org/wiki/TracWorkflow#BasicTicketWorkflowCustomization
.. _sometimes fails: https://trac.edgewall.org/wiki/TracUpgrade#AttachmentsNotMigrated
.. _the FAQ: https://trac.edgewall.org/wiki/TracFaq#Q:Attachmentsaremissingafterupgrade
.. _TicketCreationStatusPlugin: https://trac-hacks.org/wiki/TicketCreationStatusPlugin
.. _Trac environment: https://trac.edgewall.org/wiki/TracEnvironment
.. _trac-admin: https://trac.edgewall.org/wiki/TracAdmin
.. _trac-hacks.org: https://trac-hacks.org
.. _TracAdmin: https://trac.edgewall.org/wiki/TracAdmin
.. _TracDev/ApiChanges: https://trac.edgewall.org/intertrac/TracDev/ApiChanges
.. _TracDownload: https://trac.edgewall.org/intertrac/TracDownload
.. _TracFineGrainedPermissions#ReadonlyWikiPolicy: https://trac.edgewall.org/wiki/TracFineGrainedPermissions#ReadonlyWikiPolicy
.. _TracFineGrainedPermissions: https://trac.edgewall.org/wiki/TracFineGrainedPermissions#DefaultWikiPolicyandDefaultTicketPolicy
.. _TracGuide: https://trac.edgewall.org/wiki/TracGuide
.. _TracIni: https://trac.edgewall.org/wiki/TracIni
.. _TracInstall: https://trac.edgewall.org/wiki/TracInstall
.. _TracInterfaceCustomization: https://trac.edgewall.org/wiki/TracInterfaceCustomization
.. _TracMigratePlugin: https://trac-hacks.org/wiki/TracMigratePlugin
.. _TracNavigation: https://trac.edgewall.org/wiki/TracNavigation
.. _TracQuery#Filters: https://trac.edgewall.org/wiki/TracQuery#Filters
.. _TracUpgrade for 0.10: https://trac.edgewall.org/intertrac/wiki%3A0.10/TracUpgrade%23SpecificVersions
.. _TracUpgrade for 0.12: https://trac.edgewall.org/intertrac/wiki%3A0.12/TracUpgrade%23SpecificVersions
.. _version specific steps: https://trac.edgewall.org/wiki/TracUpgrade#VersionSpecificSteps
.. _WikiProcessors#AvailableProcessors: https://trac.edgewall.org/wiki/WikiProcessors#AvailableProcessors
