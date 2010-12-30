:mod:`tracopt.mimeview` -- Optional content generation modules
==============================================================

.. module :: tracopt.mimeview

Syntax Highlighters
-------------------

.. module :: tracopt.mimeview.enscript

.. autoclass :: EnscriptRenderer
.. autoclass :: EnscriptDeuglifier

   .. literalinclude:: /../tracopt/mimeview/enscript.py
      :pyobject: EnscriptDeuglifier.rules

   See also `trac.util.html.Deuglifier`.


.. module :: tracopt.mimeview.php

.. autoclass :: PHPRenderer
.. autoclass :: PhpDeuglifier

   .. literalinclude:: /../tracopt/mimeview/php.py
      :pyobject: PhpDeuglifier.rules

   See also `trac.util.html.Deuglifier`.


.. module :: tracopt.mimeview.silvercity

.. autoclass :: SilverCityRenderer



