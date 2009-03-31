Writing Tests for Core
======================

Where tests belong
------------------

If it's a regression, it belongs in :file:`trac/tests/functional/testcases.py`
for now.  Module-specific tests generally already have a
:file:`trac/$MOD/tests/functional.py` which you can add to.  The environment
is brought up as few times as possible, for speed, and your test order is
guaranteed to be run in the order it's added to the suite, at the end of the
file.

Using Twill
-----------

The definitive guide for Twill commands is the `Command Reference
<http://twill.idyll.org/commands.html>`_, but 90% of what you need is
contained by convenience methods in :class:`~trac.tests.functional.tester.FunctionalTester`\
.\ :meth:`go_to_*`\ and the following few commands:

:tc.find:
    Looks for a regex on the current page.  If it isn't found, raise an
    exception.

    Example::

        tc.find("\bPreferences\b")

:tc.notfind:
    Like find, but raises an exception if it *is* there.

    Example::

        tc.find(r"\bPreferences\b")

:tc.follow:
    Find a link matching the regex, and simulate clicking it.

    Example::

        tc.follow("Login")

:tc.fv:
    Short for `formvalue`, fill in a field.

    Example::

        tc.fv("searchform", "q", "ponies")

:tc.submit:
    Submit the active form.

    Example::

        tc.submit()

Example
-------

This is how you might construct a test that verifies that admin users can see
detailed version information.

Start with the navigation.  You shouldn't rely on the browser being in any
specific state, so begin with :meth:`FunctionalTester.go_to_*`.

::

    def test_about_page(self):
        self._tester.logout()       # Begin by logging out.
        self._tester.go_to_front()  # The homepage has a link we want
        tc.follow("About")          # Follow the link with "About" in it

        tc.find("Trac is a web-based software")
        tc.notfind("Version Info")

        self._tester.login("admin")
        self._tester.go_to_front()
        tc.follow("About")

        tc.find("Trac is a web-based software")
        tc.find("Version Info")


