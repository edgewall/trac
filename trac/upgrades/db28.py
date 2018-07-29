# -*- coding: utf-8 -*-
#
# Copyright (C) 2012-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import os.path

from trac.attachment import Attachment
from trac.util.text import exception_to_unicode, printerr, unicode_quote
from trac.util.translation import _


def do_upgrade(env, version, cursor):
    """Move attachments from the `attachments` directory into `files`, hashing
    the filenames in the process."""
    path = env.path
    old_dir = os.path.join(path, 'attachments')
    if not os.path.exists(old_dir):
        return
    old_stat = os.stat(old_dir)
    new_dir = os.path.join(path, 'files', 'attachments')
    if not os.path.exists(new_dir):
        os.makedirs(new_dir)

    cursor.execute("""
        SELECT type, id, filename FROM attachment ORDER BY type, id
        """)
    for row in cursor:
        move_attachment_file(env, *row)

    # Try to preserve permissions and ownerships of the attachments
    # directory for $ENV/files
    for dir, dirs, files in os.walk(os.path.join(path, 'files')):
        try:
            if hasattr(os, 'chmod'):
                os.chmod(dir, old_stat.st_mode)
            if hasattr(os, 'chflags') and hasattr(old_stat, 'st_flags'):
                os.chflags(dir, old_stat.st_flags)
            if hasattr(os, 'chown'):
                os.chown(dir, old_stat.st_uid, old_stat.st_gid)
        except OSError:
            pass

    # Remove empty directory hierarchy
    try:
        for dir, dirs, files in os.walk(old_dir, topdown=False):
            os.rmdir(dir)
    except OSError as e:
        env.log.warning("Can't delete old attachments directory %s: %s",
                         old_dir, exception_to_unicode(e))
        # TRANSLATOR: Wrap message to 80 columns
        printerr(_("""\
The upgrade of attachments was successful, but the old attachments directory:

  %(src_dir)s

couldn't be removed, possibly due to the presence of files that weren't
referenced in the database. The error was:

  %(exception)s

This error can be ignored, but for keeping your environment clean you should
backup any remaining files in that directory and remove it manually.
""", src_dir=old_dir, exception=exception_to_unicode(e)))


def move_attachment_file(env, parent_realm, parent_id, filename):
    old_path = os.path.join(env.path, 'attachments', parent_realm,
                            unicode_quote(parent_id))
    if filename:
        old_path = os.path.join(old_path, unicode_quote(filename))
    old_path = os.path.normpath(old_path)
    if os.path.isfile(old_path):
        new_path = Attachment._get_path(env.path, parent_realm, parent_id,
                                        filename)
        try:
            os.renames(old_path, new_path)
        except OSError:
            printerr(_("Unable to move attachment from:\n\n"
                       "  %(old_path)s\n\nto:\n\n  %(new_path)s\n",
                       old_path=old_path, new_path=new_path))
            raise
    else:
        env.log.warning("Can't find file for 'attachment:%s:%s:%s', ignoring",
                        filename, parent_realm, parent_id)
