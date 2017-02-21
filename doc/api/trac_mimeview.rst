:mod:`trac.mimeview.api` -- Trac content transformation APIs
============================================================

.. automodule :: trac.mimeview.api


Interfaces
----------

.. autoclass :: trac.mimeview.api.IHTMLPreviewRenderer
   :members:

   See also :extensionpoints:`trac.mimeview.api.IHTMLPreviewRenderer`

.. autoclass :: trac.mimeview.api.IHTMLPreviewAnnotator
   :members:

   See also :extensionpoints:`trac.mimeview.api.IHTMLPreviewAnnotator`

.. autoclass :: trac.mimeview.api.IContentConverter
   :members:

   See also :extensionpoints:`trac.mimeview.api.IContentConverter`


Components
----------

.. autoclass :: trac.mimeview.api.Mimeview
   :members:

.. autoclass :: trac.mimeview.api.ImageRenderer
   :members:

.. autoclass :: trac.mimeview.api.LineNumberAnnotator
   :members:

.. autoclass :: trac.mimeview.api.PlainTextRenderer
   :members:

.. autoclass :: trac.mimeview.api.WikiTextRenderer
   :members:


Helper classes
--------------

.. autoclass :: trac.mimeview.api.RenderingContext
   :members:

.. autoclass :: trac.mimeview.api.Context
   :members:

.. autoclass :: trac.mimeview.api.Content
   :members:


Functions
---------

.. py:function :: get_mimetype(filename, content=None, mime_map=MIME_MAP)

   Guess the most probable MIME type of a file with the given name.

   :param filename: is either a filename (the lookup will then use the suffix)
     or some arbitrary keyword.

   :param content: is either a `str` or an `unicode` string.

.. autofunction :: trac.mimeview.api.ct_mimetype

.. autofunction :: trac.mimeview.api.is_binary

.. autofunction :: trac.mimeview.api.detect_unicode

.. autofunction :: trac.mimeview.api.content_to_unicode


Sub-modules
-----------

.. automodule :: trac.mimeview.patch
   :members:

.. automodule :: trac.mimeview.pygments
   :members:

.. autoclass :: trac.mimeview.pygments.GenshiHtmlFormatter
   :members:

.. automodule :: trac.mimeview.rst
   :members:

.. automodule :: trac.mimeview.txtl
   :members:
