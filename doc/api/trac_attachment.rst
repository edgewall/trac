:mod:`trac.attachment` -- Attachments for Trac resources
========================================================

.. module :: trac.attachment

This module contains the `Attachment` model class and the
`AttachmentModule` component which manages file attachments for any
kind of Trac resources. Currently, the wiki pages, tickets and
milestones all support file attachments. You can use the same utility
methods from the `AttachmentModule` as they do for easily adding
attachments to other kinds of resources.

See also the
:download:`attach_file_form.html <../../trac/templates/attach_file_form.html>` 
and
:download:`attachment.html <../../trac/templates/attachment.html>` templates
which can be used to display the attachments.


Interfaces
----------

.. autoclass :: IAttachmentChangeListener
   :members:

.. autoclass :: IAttachmentManipulator
   :members:

.. autoclass :: ILegacyAttachmentPolicyDelegate
   :members:


Classes
-------

.. autoclass :: Attachment
   :members:

Components
----------

.. autoclass :: AttachmentModule
   :members:
