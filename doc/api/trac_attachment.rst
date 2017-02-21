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

   See also :extensionpoints:`trac.attachment.IAttachmentChangeListener`

.. autoclass :: IAttachmentManipulator
   :members:

   See also :extensionpoints:`trac.attachment.IAttachmentManipulator`

.. autoclass :: ILegacyAttachmentPolicyDelegate
   :members:

   See also :extensionpoints:`trac.attachment.ILegacyAttachmentPolicyDelegate`


Classes
-------

.. autoclass :: Attachment
   :members:

.. autoexception :: InvalidAttachment
   :members:

Components
----------

.. autoclass :: AttachmentModule
   :members:

.. autoclass :: AttachmentAdmin
   :members:
