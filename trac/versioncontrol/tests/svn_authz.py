from trac.versioncontrol import svn_authz

import unittest
import sys

def tests():
  """
  Subversion Authz File Permissions
  =================================
  
  Setup code
  ----------
  We'll use the ``make_auth`` method to create Authorizer objects
  for testing the use of authz files.  ``make_auth`` takes a module name
  and a string for the authz configuration contents.
  
  >>> from trac.versioncontrol.svn_authz import RealSubversionAuthorizer
  >>> from StringIO import StringIO
  >>> make_auth = lambda mod, cfg: RealSubversionAuthorizer(None,
  ...                   'user', mod, None, StringIO(cfg))
  
  
  Simple operation
  ----------------
  Returns 1 if no path is given:
      >>> int(make_auth('', '').has_permission(None))
      1
  
  By default read permission is not enabled:
      >>> int(make_auth('', '').has_permission('/'))
      0
  
  Read and Write Permissions
  ----------------------
  Trac is only concerned about read permissions.
      >>> a = make_auth('', '''
      ... [/readonly]
      ... user = r
      ... [/writeonly]
      ... user = w
      ... [/readwrite]
      ... user = rw
      ... [/empty]
      ... user = 
      ... ''')
  
  Permissions of 'r' or 'rw' will allow access:
      >>> int(a.has_permission('/readonly'))
      1
      >>> int(a.has_permission('/readwrite'))
      1
  
  If only 'w' permission is given, Trac does not allow access:
      >>> int(a.has_permission('/writeonly'))
      0
  
  And an empty permission does not give access:
      >>> int(a.has_permission('/empty'))
      0
  
  Trailing Slashes
  ----------------
  Checks all combinations of trailing slashes in the configuration
  or in the path parameter:
      >>> a = make_auth('', '''
      ... [/a]
      ... user = r
      ... [/b/]
      ... user = r
      ... ''')
      >>> int(a.has_permission('/a'))
      1
      >>> int(a.has_permission('/a/'))
      1
      >>> int(a.has_permission('/b'))
      1
      >>> int(a.has_permission('/b/'))
      1
  
  
  Module Usage
  ------------
  If a module name is specified, the rules used are specific to the module.
      >>> a = make_auth('module', '''
      ... [module:/a]
      ... user = r
      ... [other:/b]
      ... user = r
      ... ''')
      >>> int(a.has_permission('/a'))
      1
      >>> int(a.has_permission('/b'))
      0
  
  If a module is specified, but the configuration contains a non-module
  path, the non-module path can still apply:
      >>> int(make_auth('module', '''
      ... [/a]
      ... user = r
      ... ''').has_permission('/a'))
      1
  
  However, the module-specific rule will take precedence if both exist:
      >>> int(make_auth('module', '''
      ... [module:/a]
      ... user = 
      ... [/a]
      ... user = r
      ... ''').has_permission('/a'))
      0
  
  
  Groups and Wildcards
  --------------------
  Authz provides a * wildcard for matching any user:
      >>> int(make_auth('', '''
      ... [/a]
      ... * = r
      ... ''').has_permission('/a'))
      1
  
  Groups are specified in a separate section and used with an @ prefix:
      >>> int(make_auth('', '''
      ... [groups]
      ... grp = user
      ... [/a]
      ... @grp = r
      ... ''').has_permission('/a'))
      1

  Groups can also be members of other groups:
      >>> int(make_auth('', '''
      ... [groups]
      ... grp1 = user
      ... grp2 = @grp1
      ... [/a]
      ... @grp2 = r
      ... ''').has_permission('/a'))
      1

  Groups should not be defined cyclically, but they are handled appropriately
  to avoid infinite loops:
      >>> int(make_auth('', '''
      ... [groups]
      ... grp1 = @grp2
      ... grp2 = @grp3
      ... grp3 = @grp1, user
      ... [/a]
      ... @grp1 = r
      ... ''').has_permission('/a'))
      1
  
  If more than one group matches at the specific path, access is granted
  if any of the group rules allow access.
      >>> a = make_auth('', '''
      ... [groups]
      ... grp1 = user
      ... grp2 = user
      ... [/a]
      ... @grp1 = r
      ... @grp2 = 
      ... [/b]
      ... @grp1 = 
      ... @grp2 = r
      ... ''')
      >>> int(a.has_permission('/a'))
      1
      >>> int(a.has_permission('/b'))
      1
  
  
  Precedence
  ----------
  Precedence is user, group, then *:
      >>> a = make_auth('', '''
      ... [groups]
      ... grp = user
      ... [/a]
      ... @grp = r
      ... user = 
      ... [/b]
      ... * = r
      ... @grp = 
      ... ''')
  
  User specific permission overrides the group permission:
      >>> int(a.has_permission('/a'))
      0
  
  And group permission overrides the * permission:
      >>> int(a.has_permission('/b'))
      0
  
  The most specific matching path takes precedence:
      >>> a = make_auth('', '''
      ... [/]
      ... * = r
      ... [/b]
      ... user = 
      ... ''')
      >>> int(a.has_permission('/'))
      1
      >>> int(a.has_permission('/a'))
      1
      >>> int(a.has_permission('/b'))
      0
  
  Changeset Permissions
  ---------------------
  A test should go here for the changeset permissions.
  """

def suite():
    try:
        from doctest import DocTestSuite
        return DocTestSuite(sys.modules[__name__])
    except ImportError:
        print>>sys.stderr, "WARNING: DocTestSuite required to run these tests"
    return unittest.TestSuite()

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())

