.. index:: FastCGI
.. highlight:: apache
.. _install-fastcgi:

===============
Trac on FastCGI
===============

To generate the :file:`trac.fcgi` script run:

.. code-block:: bash

    trac-admin /path/to/env deploy /path/to/www/trac

It will be in the :file:`cgi-bin` folder inside the path given.


.. index::
    pair: FastCGI; Apache

Apache
======

Add an alias for the path you want to run Trac at to your VirtualHost::

    ScriptAlias /trac /path/to/www/trac/cgi-bin/trac.fcgi/

.. note::
    The trailing slash after the :file:`trac.fcgi` is important.

For a multiple environment configuration you will need to edit the
:file:`trac.fcgi` script. Just set **TRAC_ENV_PARENT_DIR** instead of
**TRAC_ENV**, and alter the path accordingly.

See :ref:`install-apacheauth` to setup authentication.


.. index::
    pair: FastCGI; LigHTTPD

LigHTTPD
========

An example map for using FastCGI on Lighty:

.. code-block:: none

    fastcgi.server = ("/trac" =>
                       ("trac" =>
                         ("socket" => "/tmp/trac-fastcgi.sock",
                          "bin-path" => "/path/to/www/trac/cgi-bin/trac.fcgi",
                          "check-local" => "disable",
                          "bin-environment" =>
                            ("TRAC_ENV" => "/path/to/env")
                         )
                       )
                     )

.. note::
    Be sure you do not have a trailing slash on the path you use to serve
    Trac. If you want to serve Trac from ``/``, use the following FastCGI
    script instead of the generated one:
    
    .. code-block:: python
    
        #!/usr/bin/env python
        import tempfile
        try:
            from flup.server.fcgi import WSGIServer
        except ImportError:
            from trac.web._fcgi import WSGIServer
        from trac.web.main import dispatch_request

        def application(environ, start_request):
            environ['PATH_INFO'] = environ['SCRIPT_NAME'] + environ['PATH_INFO']
            environ['SCRIPT_NAME'] = ''
            environ['PYTHON_EGG_CACHE'] = tempfile.gettempdir()
            return dispatch_request(environ, start_request)

        if __name__ == '__main__':
            WSGIServer(application).run()


.. index::
    triple: LigHTTPD; basic; authentication

Authentication
--------------

First generate your :file:`trac.htpasswd` file as shown in
:ref:`install-apacheauth-basic`.

Be sure you are loading ``mod_auth`` before ``mod_fastcgi`` in your modules
list.

You need to configure both the back-end file and the paths to enforce
authentication on:

.. code-block:: none

    auth.backend = "htpasswd"
    
    # Separated password files for each project
    # See "Conditional Configuration" 
    $HTTP["url"] =~ "^/trac" {
      auth.backend.htpasswd.userfile = "/path/to/trac.htpasswd"
    }
    
    # Enable auth on trac URLs, see
    auth.require = ("/trac/login" =>
                    ("method"  => "basic",
                     "realm"   => "Trac Login",
                     "require" => "valid-user"
                    )
                   )

.. seealso::
    
    `mod_fastcgi <http://trac.lighttpd.net/trac/wiki/Docs%3AModFastCGI>`_
        mod_fastcgi documentation.
    
    `mod_auth <http://trac.lighttpd.net/trac/wiki/Docs%3AModAuth>`_
        mod_auth documentation.


.. index::
    pair: FastCGI; nginx

nginx
=====

nginx__ handles FastCGI slightly differently, as it will not spawn the daemon
program itself. You need to start the FastCGI daemon on its own, and then
point nginx at it.

__ http://nginx.net/

An example nginx configuration:

.. code-block:: none

    location /trac {
        # full path
        if ($uri ~ ^/trac/([^/]+)(/.*)) {
             set $script_name $1;
             set $path_info $2;
        }
        
        # socket address
        fastcgi_pass   unix:/tmp/trac-fastcgi.sock;
        
        ## WSGI REQUIRED VARIABLES
        # WSGI application name - trac instance prefix. 
        fastcgi_param  SCRIPT_NAME        $script_name;
        fastcgi_param  PATH_INFO          $path_info;
        
        ## WSGI NEEDED VARIABLES - trac warns about them
        fastcgi_param  REQUEST_METHOD     $request_method;
        fastcgi_param  SERVER_NAME        $server_name;
        fastcgi_param  SERVER_PORT        $server_port;
        fastcgi_param  SERVER_PROTOCOL    $server_protocol;
        
        # for authentication to work
        fastcgi_param  REMOTE_USER        $remote_user;
    }

And a modified :file:`trac.fcgi` script:

.. code-block:: python

    #!/usr/bin/env python
    import os
    import tempfile
    
    sockaddr = '/tmp/trac-fastcgi.sock'
    os.environ['TRAC_ENV'] = '/path/to/env'
    os.environ['PYTHON_EGG_CACHE'] = tempfile.gettempdir()
    
    try:
         from trac.web.main import dispatch_request
         import trac.web._fcgi
         
         fcgiserv = trac.web._fcgi.WSGIServer(dispatch_request, 
              bindAddress = sockaddr, umask = 7)
         fcgiserv.run()
    
    except SystemExit:
        raise
    except Exception, e:
        print 'Content-Type: text/plain\r\n\r\n',
        print 'Oops...'
        print
        print 'Trac detected an internal error:'
        print
        print e
        print
        import traceback
        import StringIO
        tb = StringIO.StringIO()
        traceback.print_exc(file=tb)
        print tb.getvalue()

Authentication
--------------

To add authentication, first setup the :file:`trac.htpasswd` file as shown in
:ref:`install-apacheauth-basic`.

Then add the following in the ``location``:

.. code-block:: none

    auth_basic "Trac Login";
    auth_basic_user_file /path/to/trac.htpasswd;

.. seealso::
    
    `ngx_http_fastcgi_module <http://wiki.codemongers.com/NginxHttpFcgiModule>`_
        Documentation for the ``fastcgi_*`` configuration options.
