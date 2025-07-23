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

import asyncore
import base64
import hmac
import os
import threading
import smtpd


__all__ = ['SMTPThreadedServer']


def _b64decode(value):
    value = base64.b64decode(value)
    return str(value, 'utf-8')


def _b64encode(value):
    if isinstance(value, str):
        value = value.encode('utf-8')
    value = base64.b64encode(value)
    return str(value, 'ascii')


class SMTPChannel(smtpd.SMTPChannel):

    authmethod = None
    authenticating = None

    @property
    def user(self):
        return self.smtp_server.user

    @property
    def password(self):
        return self.smtp_server.password

    def found_terminator(self):
        line = self._emptystring.join(self.received_lines)
        if self.authenticating:
            self.received_lines = []
            self.smtp_AUTH(line)
        else:
            self.authenticating = line.split(' ', 1)[0].upper() == 'AUTH'
            super().found_terminator()

    def push(self, msg):
        if msg == '250 HELP':
            super().push('250-AUTH ' + self.authmethod)
        super().push(msg)
        if self.authenticating and not msg.startswith('3'):
            self.authenticating = False
        if msg.startswith('5'):
            self.close_when_done()


class SMTPChannelAuthPlain(SMTPChannel):

    authmethod = 'PLAIN'

    def smtp_AUTH(self, arg):
        values = arg.split(' ', 1)
        if len(values) == 0 or values[0] != self.authmethod:
            self.push('535 Authentication failed')
            return
        try:
            creds = _b64decode(values[1])
        except:
            self.push('535 Authentication failed')
            return
        creds = creds.split('\0')
        if len(creds) != 3 or len(creds[0]) != 0 and creds[0] != creds[1]:
            self.push('535 Authentication failed')
            return
        user = creds[1]
        password = creds[2]
        if self.user == user and self.password == password:
            self.push('235 Authentication successful')
        else:
            self.push('535 Authentication failed')


class SMTPChannelAuthLogin(SMTPChannel):

    authmethod = 'LOGIN'
    incoming_user = None

    def smtp_AUTH(self, arg):
        if self.incoming_user:
            try:
                password = _b64decode(arg)
            except:
                password = None
            if self.incoming_user == self.user and password == self.password:
                self.push('235 Authentication successful')
            else:
                self.push('535 Authentication failed')
            return

        values = arg.split(' ', 1)
        if len(values) == 0:
            self.push('535 Authentication failed')
            return

        if values[0] == self.authmethod:
            if len(values) == 2:
                try:
                    self.incoming_user = _b64decode(values[1])
                except:
                    self.push('535 Authentication failed')
                    return
                self.push('334 ' + _b64encode('Password'))
            else:
                self.push('334 ' + _b64encode('Username'))
        else:
            try:
                self.incoming_user = _b64decode(values[0])
            except:
                self.push('535 Authentication failed')
                return
            self.push('334 ' + _b64encode('Password'))


class SMTPChannelAuthCramMd5(SMTPChannel):

    authmethod = 'CRAM-MD5'
    challenge = None

    def smtp_AUTH(self, arg):
        if self.challenge:
            try:
                user, hash_ = _b64decode(arg).split(' ', 1)
            except:
                self.push('535 Authentication failed')
                return
            rehash = hmac.HMAC(self.password.encode('utf-8'), self.challenge,
                               'md5').hexdigest()
            if user == self.user and hash_ == rehash:
                self.push('235 Authentication successful')
            else:
                self.push('535 Authentication failed')
            return
        else:
            self.challenge = os.urandom(64)
            self.push('334 ' + _b64encode(self.challenge))


class SMTPServer(smtpd.SMTPServer):

    user = None
    password = None
    message = None

    def __init__(self, localaddr, **kwargs):
        if 'channel_class' in kwargs:
            self.channel_class = kwargs.pop('channel_class') or \
                                 smtpd.SMTPChannel
        if 'user' in kwargs:
            self.user = kwargs.pop('user')
        if 'password' in kwargs:
            self.password = kwargs.pop('password')
        super().__init__(localaddr, None, decode_data=True, **kwargs)

    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        kwargs['peer'] = peer
        kwargs['mailfrom'] = mailfrom
        kwargs['rcpttos'] = rcpttos
        kwargs['data'] = data.replace('\n', '\r\n')
        self.message = kwargs

    def clear_message(self):
        self.message = None


class SMTPThreadedServer(threading.Thread):
    """
    Run a SMTP server for a single connection, within a dedicated thread
    """
    host = '127.0.0.1'
    port = None
    socket_map = None
    server = None
    authmethod = None
    user = None
    password = None
    authchannels = {
        'PLAIN': SMTPChannelAuthPlain,
        'LOGIN': SMTPChannelAuthLogin,
        'CRAM-MD5': SMTPChannelAuthCramMd5,
    }

    def __init__(self, port, authmethod=None, user=None, password=None):
        self.port = port
        self.authmethod = authmethod
        self.user = user
        self.password = password
        self.socket_map = {}
        super().__init__(target=asyncore.loop,
                         args=(0.1, True, self.socket_map))
        self.daemon = True

    def start(self):
        channel_class = self.authchannels.get(self.authmethod)
        self.server = SMTPServer((self.host, self.port), map=self.socket_map,
                                  channel_class=channel_class,
                                  user=self.user, password=self.password)
        super().start()

    def stop(self):
        self.server.close()
        self.join()

    def get_sender(self):
        message = self.server.message
        return message and message['mailfrom']

    def get_recipients(self):
        message = self.server.message
        return message['rcpttos'] if message else []

    def get_message(self):
        message = self.server.message
        return message and message['data']

    def cleanup(self):
        self.server.clear_message()
