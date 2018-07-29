# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

# Imports for backward compatibility
from trac.notification.api import IEmailSender, NotificationSystem
from trac.notification.compat import Notify, NotifyEmail
from trac.notification.mail import (EMAIL_LOOKALIKE_PATTERN, MAXHEADERLEN,
                                    SmtpEmailSender, SendmailEmailSender)
