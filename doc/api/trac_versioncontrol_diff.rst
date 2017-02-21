:mod:`trac.versioncontrol.diff` -- Utilities for generation of diffs
====================================================================

.. automodule :: trac.versioncontrol.diff

Synopsis
--------

`get_filtered_hunks`, `get_hunks` are low-level wrappers for Python's
`difflib.SequenceMatcher`, and they generate groups of opcodes
corresponding to diff "hunks".

`get_change_extent` is a low-level utility used when marking
intra-lines differences.

`diff_blocks` is used at a higher-level to fill the template data
needed by the "diff_div.html" template.

`unified_diff` is also a higher-level function returning differences
following the `unified diff`_ file format.

Finally, `get_diff_options` is an utility for retrieving user diff
preferences from a `~trac.web.api.Request`.

.. _unified diff: http://www.gnu.org/software/hello/manual/diff/Detailed-Unified.html

Function Reference
------------------

.. autofunction :: get_change_extent
.. autofunction :: get_filtered_hunks
.. autofunction :: get_hunks
.. autofunction :: hdf_diff
.. autofunction :: diff_blocks
.. autofunction :: unified_diff
.. autofunction :: get_diff_options
.. autofunction :: filter_ignorable_lines
