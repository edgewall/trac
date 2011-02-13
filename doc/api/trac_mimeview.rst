:mod:`trac.mimeview.api` -- Trac content transformation APIs
============================================================

.. automodule :: trac.mimeview.api

Interfaces
----------

.. autoclass :: trac.mimeview.api.IHTMLPreviewRenderer
   :members:

.. autoclass :: trac.mimeview.api.IHTMLPreviewAnnotator
   :members:

.. autoclass :: trac.mimeview.api.IContentConverter
   :members:

Components
----------

.. autoclass :: trac.mimeview.api.Mimeview
   :members:
 
Helper classes
--------------

.. autoclass :: trac.mimeview.api.RenderingContext
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

.. autofunction :: trac.mimeview.api.is_binary

.. autofunction :: trac.mimeview.api.detect_unicode

.. autofunction :: trac.mimeview.api.content_to_unicode

