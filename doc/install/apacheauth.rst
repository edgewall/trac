.. index::
    pair: Apache; authentication
.. highlight:: apache
.. _install-apacheauth:

========================
Authentication on Apache
========================

.. index::
    triple: Apache; basic; authentication
.. _install-apacheauth-basic:

Basic Authentication
====================

Create the htpasswd file using the program of the same name:

.. code-block:: bash

    htpasswd -c trac.htpasswd $USERNAME

Then add the following to your VirtualHost::

    <Location /trac/login>
        AuthType Basic
        AuthName "Trac Login"
        AuthUserFile /path/to/trac.htpasswd
        Require valid-user
    </Location>

The ``AuthName`` can be set to whatever you like, and will shown to the user
in the authentication dialog in their browser.

In a multiple environment setup, you can use the following to use the same
authentication on all environments::

    <LocationMatch /trac/[^/]+/login>
        AuthType Basic
        AuthName "Trac Login"
        AuthUserFile /path/to/htpasswd
        Require valid-user
    </LocationMatch>

.. seealso::
    
    `Authentication, Authorization and Access Control <http://httpd.apache.org/docs/2.2/howto/auth.html>`_
        Apache guide to setting up authentication.
    
    `mod_auth_basic <http://httpd.apache.org/docs/2.2/mod/mod_auth_basic.html>`_
        Documentation for mod_auth_basic.

.. index::
    triple: Apache; digest; authentication

Digest Authentication
=====================

Create the htdigest file as with basic:

.. code-block:: bash

    htdigest -c trac.htdigest realm $USERNAME

``realm`` needs to match the value of ``AuthName`` used in the configuration.


Then add the following to your VirtualHost::

    <Location /trac/login>
        AuthType Digest
        AuthName "realm"
        AuthDigestFile /path/to/trac.htdigest
        Require valid-user
    </Location>

You can use the same ``LocationMatch`` as above for multiple environments.

.. seealso::

    `mod_auth_digest <http://httpd.apache.org/docs/2.2/mod/mod_auth_digest.html>`_
        Documentation for mod_auth_digest.


.. index::
    triple: Apache; LDAP; authentication

LDAP Authentication
===================

You can use ``mod_authnz_ldap`` to authenticate against an LDAP directory.

Add the following to your VirtualHost::

    <Location /trac/login>
        AuthType Basic
        AuthName "Trac Login"
        AuthBasicProvider ldap
        AuthLDAPURL "ldap://127.0.0.1/dc=example,dc=com?uid?sub?(objectClass=inetOrgPerson)"
        AuthzLDAPAuthoritative Off
        Require valid-user
    </Location>

You can also require the user be a member of a certain LDAP group, instead of
just having a valid login::

    Require ldap-group CN=Trac Users,CN=Users,DC=example,DC=com

.. index::
    triple: Apache; Active Directory; authentication

Windows Active Directory
------------------------

You can use LDAP as a way to authenticate to a AD server.

Use the following as your LDAP URL::

    AuthLDAPURL "ldap://directory.example.com:3268/DC=example,DC=com?sAMAccountName?sub?(objectClass=user)"

You will also need to provide an account for Apache to use when checking
credentials. As this password will be listed in plaintext in the
config, you should be sure to use an account specifically for this task::

    AuthLDAPBindDN ldap-auth-user@example.com
    AuthLDAPBindPassword "password"

.. seealso::
    
    `mod_authnz_ldap <http://httpd.apache.org/docs/2.2/mod/mod_authnz_ldap.html>`_
        Documentation for mod_authnz_ldap.
    
    `mod_ldap <http://httpd.apache.org/docs/2.2/mod/mod_ldap.html>`_
        Documentation for mod_ldap, which provides connection pooling and a
        shared cache.
    
    `LdapPlugin <http://trac-hacks.org/wiki/LdapPlugin>`_
        Store :ref:`Trac permissions <admin-permissions>` in LDAP.


.. index::
    triple: Apache; SSPI; authentication

SSPI Authentication
===================

If you are using Apache on Windows, you can use mod_auth_sspi to provide
single-sign-on. Download the module `from its webpage`__ and then add the
following to your VirtualHost::

    <Location /trac/login>
        AuthType SSPI
        AuthName "Trac Login"
        SSPIAuth On
        SSPIAuthoritative On
        SSPIDomain MyLocalDomain
        SSPIOfferBasic On
        SSPIOmitDomain Off
        SSPIBasicPreferred On
        Require valid-user
    </Location>

__ http://sourceforge.net/project/showfiles.php?group_id=162518

Using the above, usernames in Trac will be of the form ``DOMAIN\username``, so
you may have to re-add permissions and such. If you do not want the domain to
be part of the username, set ``SSPIOmitDomain On`` instead.

.. note::
    Version 1.0.2 and earlier of mod_auth_sspi do not support SSPIOmitDomain
    and have bug in basic authentication. >= 1.0.3 is recommended.

.. seealso::
    
    `mod_auth_sspi <http://mod-auth-sspi.sourceforge.net/>`_
        Apache 2.x SSPI authentication module.
    Some common problems with SSPI authentication
        `#1055 <http://trac.edgewall.org/ticket/1055>`_,
        `#1168 <http://trac.edgewall.org/ticket/1168>`_,
        `#3338 <http://trac.edgewall.org/ticket/3338>`_
        
