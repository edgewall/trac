.. charset=utf-8

Upgrade Instructions
====================


Instructions
------------

Typically, there are seven steps involved in upgrading to a newer
version of Trac:


1. Check your plugins
~~~~~~~~~~~~~~~~~~~~~

Check whether your plugins are compatible with the version of Trac
that you are upgrading to. Obsolete plugins listed in the `version
specific steps`_ below should be uninstalled or disabled.

If you are upgrading to a minor release, plugin compatibility is
usually not a concern because the Trac API typically does not change,
and major features are not introduced, for minor releases.

If your plugins are installed from `​trac-hacks.org`_ you can check
compatibility by looking for a tag on the project page corresponding
to a major release (e.g. `1.2`). If you are unsure, you'll want to
contact the plugin author or ask on the `​MailingList`_.

If you are running several Trac plugins it is good to test the upgrade
and site functionality in a staging instance of your site before
upgrading your production instance. Remember, plugin authors are
responsible for Trac version compatibility and plugins can interact in
unexpected ways. Your Trac instance may have a unique combination of
plugins and therefore it's a good idea to do some verification testing
when making any changes to your site.


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
`​TracDownload`_. If your Trac instance was installed through an
operating system package manager or an installer on Windows, proceed
with the standard steps that are appropriate for your operating
system.

If you are managing your Trac installation using command line tools,
`pip` is the preferred tool to upgrade a Trac instance because it will
uninstall the old version. The following command will upgrade your
Trac installation using the package published to `​PyPI`_.


::

    $ pip install --upgrade Trac


The upgrade command will give you the latest release of Trac. If
instead you wish to upgrade to a different version, such as a minor
release of Trac when there is a newer major release available, then
specify the Trac version in the `pip` command.


::

    $ pip install --upgrade Trac==1.2.1


You should also upgrade dependencies so they are compliant with the
`required versions`_ and upgrade Trac plugins.


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

Note that a backup of your database will be performed automatically
prior to the upgrade. The backup is saved in the location specified by
`[trac]` `backup_dir`.


5. Update the Trac Documentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, every `Trac environment`_ includes a copy of the Trac
documentation for the installed version. However, to keep the included
documentation in sync with the installed version of Trac, use the
following `trac-admin`_ command to upgrade the documentation:


::

    $ trac-admin /path/to/projenv wiki upgrade


Note that this procedure will leave your `WikiStart`, `TracGuide` and
`SandBox` pages unaltered. Local changes to other pages that are
distributed with Trac will be overwritten.


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
not mandatory, but makes it easier to troubleshoot issues later on, as
your installation is uncluttered by code or templates from a previous
release that is not used anymore. As usual, make a backup before
deleting the directory.

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

`​PyMySQL`_ is the supported MySQL database library, support for
`​MySQL-python`_ has been removed.


Obsolete Plugins
++++++++++++++++

Trac has added functionality equivalent to the following plugins:


+ `​DynamicVariablesPlugin`_: dynamic variables are autocompleted
+ `​NavAddPlugin`_: see `TracNavigation`_
+ `​FlexibleAssignToPlugin`_: subclass `ConfigurableTicketWorkflow`
  and override `get_allowed_owners`
+ `​TracMigratePlugin`_: Use `TracAdmin`_ `convert_db` command


The plugins should be removed when upgrading Trac to 1.4.


Jinja2 is the new template engine
+++++++++++++++++++++++++++++++++

In Trac itself, all the content is now generated by using the Jinja2
template engine. You may want to verify that your plugins are
compatible with this change. (TODO: expand...)

If you customized the Trac templates, or the site.html template,
you'll need to adapt that as well. (TODO: expand...) See
`#CustomizedTemplates`_

Another "template" that will probably need to be updated are the
e-mail notification summaries, defined in the ` trac.ini,
[notification] section`_, for the `batch_subject_template` and
`ticket_subject_template` settings.

For example:


::

    [notification]
    ticket_subject_template = ${prefix} #${ticket.id}: ${summary}


(instead of `$prefix #$ticket.id: $summary`)


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

The ticket enums now have a <em>description</em> field. An
<em>ambiguous column name</em> error may be seen for reports that
reference the `description` column of another table and join the
`enum` table with that table (e.g. `ticket`, `component`). The reports
{1}, {2}, {3}, {4}, {5}, {7}, and {8} are modified by an upgrade step
to fix the issue, but the modification may not succeed if the default
reports have been modified, in which case `upgrade` will output a
message to the terminal instructing the user to modify the reports.
User-created reports may also need to be modified.

Reports that display the error need to be modified to prefix the
`description` column with the appropriate table name or alias. For
example, if the `ticket` table is aliased as `t` ( `ticket t` or
`ticket AS t`), replace `description` with `t.description` if the
report should use the ticket's `description` column.


Upgrading from Trac 1.0 to 1.2
``````````````````````````````


Python 2.5 no longer supported
++++++++++++++++++++++++++++++

Upgrade Python to at least 2.6 or 2.7, but not 3.0 or greater.


Obsolete Plugins
++++++++++++++++

Trac has added functionality equivalent to the following plugins:


+ `​AdminEnumListPlugin`_
+ `​DateFieldPlugin`_: see the time `custom field type`_
+ `​GroupBasedRedirectionPlugin`_: the default handler can set as a
  user preference.
+ `​LinenoMacro`_: see `WikiProcessors#AvailableProcessors`_
+ `​NeverNotifyUpdaterPlugin`_: see `notification subscribers`_
+ `​QueryUiAssistPlugin`_: see `TracQuery#Filters`_.
+ `​TicketCreationStatusPlugin`_: see `#NewWorkflowActions`_


The plugins should be removed when upgrading Trac to 1.2.


New workflow actions
++++++++++++++++++++

The ticket creation step is controlled with a workflow action. The
default workflow has `create` and `create_and_assign` actions. The
`create` action will always be added when upgrading the database. The
`create_and_assign` action will be added if the workflow has an
<em>assigned</em> state. You may want to edit your workflow after
upgrading the database to customize the actions available on the
<em>New Ticket</em> page.


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


+ `​BatchModifyPlugin`_
+ ​`​GitPlugin`_
+ `​OverrideEditPlugin`_


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
<em>not</em> attachments, the last step of the migration to the new
layout will not be completed: the deletion of the now unused
`attachments` directory can't be done if there are still files and
folders in it. You may ignore this error, but better to move them
elsewhere and remove the `attachments` directory manually. The
attachments themselves are now all located in your environment below
the `files/attachments` directory.


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
`​wiki:0.12/TracUpgrade#SpecificVersions`_.

For upgrades from versions older than Trac 0.10, refer first to
`​wiki:0.10/TracUpgrade#SpecificVersions`_.


Known Issues
------------


Customized Templates
~~~~~~~~~~~~~~~~~~~~

Trac supports customization of its templates by placing copies of the
templates in the `<env>/templates` folder of your `environment`_ or in
a common location specified in the ` [inherit] templates_dir`_
configuration setting. If you choose to do so, be aware that you will
need to repeat your changes manually on a copy of the new templates
when you upgrade to a new release of Trac (even a minor one), as the
templates will likely evolve. So keep a diff around.

The preferred way to perform `TracInterfaceCustomization`_ is a custom
plugin doing client-side JavaScript transformation of the generated
output, as this is more robust in case of changes: we usually won't
modify an element `id` or change its CSS `class`, and if we have to do
so, this will be documented in the `​TracDev/ApiChanges`_ pages.


ZipImportError
~~~~~~~~~~~~~~

Due to internal caching of zipped packages, whenever the content of
the packages change on disk, the in-memory zip index will no longer
match and you'll get irrecoverable ZipImportError errors. Better
anticipate and bring your server down for maintenance before
upgrading. See `​#7014`_ for details.


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
been found. If you encounter this issue, see `​the FAQ`_ for a
workaround and please report your findings to `​#11370`_.


Related topics
--------------


Upgrading Python
~~~~~~~~~~~~~~~~

Upgrading Python to a newer version will require reinstallation of
Python packages: Trac itself of course, but also `​setuptools`_. If
you are using Subversion, you'll need to upgrade the `​Python bindings
for SVN`_.


Changing Database Backend
~~~~~~~~~~~~~~~~~~~~~~~~~

The `​TracMigratePlugin`_ on `​trac-hacks.org`_ has been written to
assist in migrating between SQLite, MySQL and PostgreSQL databases.


See also: `TracGuide`_, `TracInstall`_

.. _ [inherit] templates_dir: http://trac.edgewall.org/wiki/TracIni#GlobalConfiguration
.. _ trac.ini, [notification] section: http://trac.edgewall.org/wiki/TracIni#notification-section
.. _#11370: http://trac.edgewall.org/intertrac/%2311370
.. _#7014: http://trac.edgewall.org/intertrac/%237014
.. _#CustomizedTemplates: http://trac.edgewall.org/wiki/TracUpgrade#CustomizedTemplates
.. _#NewWorkflowActions: http://trac.edgewall.org/wiki/TracUpgrade#NewWorkflowActions
.. _AdminEnumListPlugin: https://trac-hacks.org/wiki/AdminEnumListPlugin
.. _backup your environment: http://trac.edgewall.org/wiki/TracBackup
.. _BatchModifyPlugin: https://trac-hacks.org/wiki/BatchModifyPlugin
.. _custom field type: http://trac.edgewall.org/wiki/TracTicketsCustomFields#AvailableFieldTypesandOptions
.. _DateFieldPlugin: https://trac-hacks.org/wiki/DateFieldPlugin
.. _deploy command: http://trac.edgewall.org/wiki/TracInstall#MappingStaticResources
.. _DynamicVariablesPlugin: https://trac-hacks.org/wiki/DynamicVariablesPlugin
.. _environment: http://trac.edgewall.org/wiki/TracEnvironment
.. _FlexibleAssignToPlugin: https://trac-hacks.org/wiki/FlexibleAssignToPlugin
.. _GitPlugin: https://trac-hacks.org/wiki/GitPlugin
.. _GroupBasedRedirectionPlugin: https://trac-hacks.org/wiki/GroupBasedRedirectionPlugin
.. _hotcopy: http://trac.edgewall.org/wiki/TracBackup
.. _internal errors: http://trac.edgewall.org/wiki/TracUpgrade#ZipImportError
.. _LinenoMacro: https://trac-hacks.org/wiki/LinenoMacro
.. _MailingList: http://trac.edgewall.org/intertrac/MailingList
.. _migrated: http://trac.edgewall.org/wiki/TracUpgrade#AttachmentsMigrated
.. _MySQL-python: https://pypi.python.org/pypi/MySQL-python
.. _NavAddPlugin: https://trac-hacks.org/wiki/NavAddPlugin
.. _NeverNotifyUpdaterPlugin: https://trac-hacks.org/wiki/NeverNotifyUpdaterPlugin
.. _notification subscribers: http://trac.edgewall.org/wiki/TracNotification#notification-subscriber-section
.. _OverrideEditPlugin: https://trac-hacks.org/wiki/OverrideEditPlugin
.. _PyMySQL: https://pypi.python.org/pypi/PyMySQL
.. _PyPI: https://pypi.python.org/pypi/Trac
.. _Python bindings for SVN: http://trac.edgewall.org/intertrac/TracSubversion
.. _QueryUiAssistPlugin: https://trac-hacks.org/wiki/QueryUiAssistPlugin
.. _ReadonlyWikiPolicy: http://trac.edgewall.org/wiki/TracUpgrade#Newpermissionspolicyforread-onlywikipages
.. _required versions: http://trac.edgewall.org/wiki/TracInstall#Dependencies
.. _setuptools: http://pypi.python.org/pypi/setuptools
.. _sometimes fails: http://trac.edgewall.org/wiki/TracUpgrade#AttachmentsNotMigrated
.. _the FAQ: https://trac.edgewall.org/wiki/TracFaq#Q:Attachmentsaremissingafterupgrade
.. _TicketCreationStatusPlugin: https://trac-hacks.org/wiki/TicketCreationStatusPlugin
.. _Trac environment: http://trac.edgewall.org/wiki/TracEnvironment
.. _trac-admin: http://trac.edgewall.org/wiki/TracAdmin
.. _trac-hacks.org: https://trac-hacks.org
.. _TracAdmin: http://trac.edgewall.org/wiki/TracAdmin
.. _TracDev/ApiChanges: http://trac.edgewall.org/intertrac/TracDev/ApiChanges
.. _TracDownload: http://trac.edgewall.org/intertrac/TracDownload
.. _TracFineGrainedPermissions#ReadonlyWikiPolicy: http://trac.edgewall.org/wiki/TracFineGrainedPermissions#ReadonlyWikiPolicy
.. _TracFineGrainedPermissions: http://trac.edgewall.org/wiki/TracFineGrainedPermissions#DefaultWikiPolicyandDefaultTicketPolicy
.. _TracGuide: http://trac.edgewall.org/wiki/TracGuide
.. _TracIni: http://trac.edgewall.org/wiki/TracIni
.. _TracInstall: http://trac.edgewall.org/wiki/TracInstall
.. _TracInterfaceCustomization: http://trac.edgewall.org/wiki/TracInterfaceCustomization
.. _TracMigratePlugin: https://trac-hacks.org/wiki/TracMigratePlugin
.. _TracNavigation: http://trac.edgewall.org/wiki/TracNavigation
.. _TracQuery#Filters: http://trac.edgewall.org/wiki/TracQuery#Filters
.. _version specific steps: http://trac.edgewall.org/wiki/TracUpgrade#VersionSpecificSteps
.. _wiki:0.10/TracUpgrade#SpecificVersions: http://trac.edgewall.org/intertrac/wiki%3A0.10/TracUpgrade%23SpecificVersions
.. _wiki:0.12/TracUpgrade#SpecificVersions: http://trac.edgewall.org/intertrac/wiki%3A0.12/TracUpgrade%23SpecificVersions
.. _WikiProcessors#AvailableProcessors: http://trac.edgewall.org/wiki/WikiProcessors#AvailableProcessors
