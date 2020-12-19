:mod:`trac.notification.mail` -- Utilities for building and sending email
=========================================================================

Building email messages
-----------------------

.. module :: trac.notification.mail

Trac provides functions to build email messages. To build a
message that contains both a html version and a text version::

  # use the default charset settings from the trac conf
  charset = create_charset(env.config.get('notification', 'mime_encoding'))

  # create a multipart message, with the 'alternative' subtype
  message = create_mime_multipart('alternative')

  # raw messages
  message_html = "<p>This is a <em>Trac</em> generated e-mail</p>"
  message_text = "This is a Trac generated e-mail"

  # convert messages to mime text
  mime_html = create_mime_text(message_html, "html", charset)
  mime_text = create_mime_text(message_text, "plain", charset)

  # attach both parts to the message
  message.attach(mime_html)
  message.attach(mime_text)

  # create a dict of headers
  headers = {
    "From": ("Trac installation", "noreply@ourcompany.com"),
    "To": ("Intended Recipient", "recipient@ourcompany.com"),
    "Subject": "You have been sent a generated message",
    "Date": email.utils.formatdate()
  }

  # attach headers to the message
  for k, v in headers:
    set_header(message, k, v, charset)

After building the message, you will probably want to use
`NotificationSystem.send_email()` to send the message using the
email distribution method that is configured for your Trac instance.

The following functions are useful when building mail messages:

.. autofunction :: create_charset

.. autofunction :: create_header

.. autofunction :: create_message_id

.. autofunction :: create_mime_multipart

.. autofunction :: create_mime_text

.. autofunction :: get_from_author

.. autofunction :: set_header

Getting the email address for a username
----------------------------------------

If you are manually generating email messages, and thus are bypassing
the email generation done through `NotificationEvent`, formatters and
`EmailDistributor`, you may want to find the email address and the real
name of a Trac user to use in the "To" header of your email message.
`RecipientMatcher` will resolve user names into real names and email
addresses, and vice versa.

.. autoclass :: RecipientMatcher
   :members:

Other Components
----------------

There are a number of other components that are defined in this module.
You will most likely not use these when writing your own plugins and extensions.

.. autoclass :: AlwaysEmailSubscriber

.. autoclass :: EmailDistributor

.. autoclass :: FromAuthorEmailDecorator

.. autoclass :: SendmailEmailSender

.. autoclass :: SessionEmailResolver

.. autoclass :: SmtpEmailSender
