:mod:`trac.util` -- General purpose utilities
=============================================

.. module :: trac.util

The `trac.util` package is a hodgepodge of various categories of
utilities.  If a category contains enough code in itself, it earns a
sub-module on its own, like the following ones:

.. toctree::
   :maxdepth: 1
   :glob:

   trac_util_*


Otherwise, the functions are direct members of the `trac.util` package
(i.e. placed in the "__init__.py" file).

Web related utilities
---------------------

.. autofunction :: trac.util.get_reporter_id
.. autofunction :: trac.util.content_disposition

OS related utilies
------------------

.. autofunction :: copytree
.. autofunction :: create_file
.. autofunction :: create_unique_file
.. autofunction :: getuser
.. autofunction :: is_path_below
.. autofunction :: makedirs
.. autofunction :: read_file
.. autofunction :: rename
.. autofunction :: terminate
.. autofunction :: touch_file

.. autoclass :: AtomicFile
   :members:
.. autoclass :: NaivePopen
   :members:

.. autoexception :: WindowsError

   Also defined on non-Windows systems (by a dummy OSError subclass).

.. autoclass :: file_or_std

.. data :: urandom

  The standard `os.urandom` when available, otherwise a reasonable
  replacement.


Python "system" utilities
-------------------------

Complements the `inspect`, `traceback` and `sys` modules.

.. autofunction :: fq_class_name
.. autofunction :: arity
.. autofunction :: get_last_traceback
.. autofunction :: get_lines_from_file
.. autofunction :: get_frame_info
.. autofunction :: import_namespace
.. autofunction :: safe__import__
.. autofunction :: safe_repr
.. autofunction :: get_doc


Setuptools utilities
--------------------

.. autofunction :: get_module_path
.. autofunction :: get_sources
.. autofunction :: get_pkginfo


Cryptographic related utilities
-------------------------------

.. autofunction :: hex_entropy
.. autofunction :: md5crypt
.. autofunction :: salt


Data structures which don't fit anywhere else
---------------------------------------------

.. autoclass :: Ranges
   :members:

.. autofunction :: create_zipinfo
.. autofunction :: to_ranges
.. autofunction :: to_list

.. autoclass :: lazy


Algorithmic utilities
---------------------

.. autofunction :: embedded_numbers
.. autofunction :: partition
.. autofunction :: as_int
.. autofunction :: as_bool
.. autofunction :: pathjoin
.. autofunction :: sub_val
