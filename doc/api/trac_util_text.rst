.. -*- coding: utf-8 -*-

:mod:`trac.util.text` -- Text manipulation
==========================================
.. module :: trac.util.text

The Unicode toolbox
-------------------

Trac internals are almost exclusively dealing with Unicode text,
represented by `unicode` instances. The main advantage of using
`unicode` over UTF-8 encoded `str` (as this used to be the case before
version 0.10), is that text transformation functions in the present
module will operate in a safe way on individual characters, and won't
risk to eventually cut a multi-byte sequence in the middle. Similar
issues with Python string handling routines are avoided as well, like
surprising results when splitting text in lines. For example, did you
know that e.g. "Priorità" is encoded as ``'Priorit\xc3\x0a'`` in
UTF-8? Stripping this in some locales can cut away the trailing
``\x0a``...

The drawback is that most of the outside world, while eventually
"Unicode", is definitely not `unicode`. This is why we need to convert
back and forth between `str` and `unicode` at the boundaries of the
system. And more often than not we even have to guess which encoding
is used in the incoming `str` strings.

Encoding `unicode` to `str` is usually directly performed by calling
`encode()` on the `unicode` instance, while decoding is preferably
left to the `to_unicode` helper function, which converts `str` to
`unicode` in a robust, guaranteed successful way.

.. autofunction :: to_unicode

.. autofunction :: exception_to_unicode

.. autofunction :: unicode_quote

.. autofunction :: unicode_quote_plus

.. autofunction :: unicode_unquote

.. autofunction :: unicode_urlencode

.. class :: unicode_passwd

.. autofunction :: console_print

.. autofunction :: printout

.. autofunction :: printerr

.. autofunction :: raw_input

.. autofunction :: to_utf8

.. data :: empty

   A special tag object evaluating to the empty string, used as marker
   for missing value (as opposed to a present but empty value).

Text formatting
---------------

.. autofunction :: breakable_path

.. autofunction :: expandtabs

.. autofunction :: normalize_whitespace

.. autofunction :: obfuscate_email_address

.. autofunction :: pretty_size

.. autofunction :: print_table

.. autofunction :: shorten_line

.. autofunction :: unquote_label

.. autofunction :: wrap
