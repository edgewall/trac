# -*- coding: utf-8 -*-
#
# Copyright (C) 2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#

import asyncio
import hmac
import logging
import random
import threading

from aiosmtpd.controller import UnthreadedController
from aiosmtpd.handlers import Message
from aiosmtpd.smtp import AuthResult, LoginPassword, SMTP, log

log.addHandler(logging.NullHandler())  # make warnings from aiosmtpd.smtp quiet


__all__ = ['SMTPThreadedServer']


class SMTPFixup(SMTP):

    _randinst = random.Random()
    if hasattr(_randinst, 'randbytes'):
        def _randbytes(self, n):
            return self._randinst.randbytes(n)
    else:
        def _randbytes(self, n):
            return self._randinst.getrandbits(n * 8).to_bytes(n, 'little')

    async def auth_CRAM__MD5(self, _, args):
        challenge = self._randbytes(64)
        response = await self.challenge_auth(challenge)
        user, hash_ = response.split(b' ', 1)
        h = hmac.HMAC(self._authenticator.password, challenge, 'md5')
        success = user == self._authenticator.user and \
                  hash_ == h.hexdigest().encode('ascii')
        return AuthResult(success=success, handled=False)


class Authenticator(object):

    user = None
    password = None
    authmethod = None

    def __init__(self, user, password, authmethod):
        self.user = user.encode('utf-8')
        self.password = password.encode('utf-8')
        self.authmethod = authmethod

    def __call__(self, server, session, envelope, mechanism, auth_data):
        failed = AuthResult(success=False, handled=False)
        if mechanism != self.authmethod:
            return failed
        if not isinstance(auth_data, LoginPassword):
            return failed
        success = auth_data.login == self.user and \
                  auth_data.password == self.password
        return AuthResult(success=success, handled=False)


class Handler(Message):

    server = None

    def __init__(self, server):
        self.server = server

    def handle_message(self, message):
        pass

    def prepare_message(self, session, envelope):
        self.server._set_envelope(envelope)
        return None


class Controller(UnthreadedController):

    def factory(self):
        return SMTPFixup(self.handler, **self.SMTP_kwargs)

    def _create_server(self):
        return self.loop.create_server(
            self._factory_invoker, host=self.hostname, port=self.port,
            ssl=self.ssl_context, reuse_address=True)


class SMTPThreadedServer(threading.Thread):
    """
    Run a SMTP server for a single connection, within a dedicated thread
    """
    host = '127.0.0.1'
    port = None
    authmethod = None
    user = None
    password = None
    envelope = None
    loop = None
    controller = None

    def __init__(self, port, authmethod=None, user=None, password=None):
        self.port = port
        self.authmethod = authmethod
        self.user = user
        self.password = password
        loop = asyncio.new_event_loop()
        if authmethod:
            authenticator = Authenticator(user, password, authmethod)
            auth_exclude_mechanism = set(('PLAIN', 'LOGIN', 'CRAM-MD5'))
            auth_exclude_mechanism.discard(authmethod)
        else:
            authenticator = None
            auth_exclude_mechanism = None
        handler = Handler(self)
        controller = Controller(handler, loop=loop, hostname=self.host,
                                port=port, authenticator=authenticator,
                                auth_exclude_mechanism=auth_exclude_mechanism,
                                auth_require_tls=False)
        self.loop = loop
        self.controller = controller
        controller.begin()
        super().__init__(target=loop.run_forever)
        self.daemon = True

    def stop(self):
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        while self.is_alive():
            self.join(0.1)
        self.controller.end()
        self.loop.close()

    def _set_envelope(self, envelope):
        self.envelope = envelope

    def get_sender(self):
        return self.envelope.mail_from if self.envelope else None

    def get_recipients(self):
        return self.envelope.rcpt_tos if self.envelope else []

    def get_message(self):
        if self.envelope:
            content = self.envelope.content
            if content.endswith(b'\r\n'):
                content = content[:-2]
            return str(content, 'utf-8')

    def cleanup(self):
        self.envelope = None
