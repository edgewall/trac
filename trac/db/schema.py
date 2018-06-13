# -*- coding: utf-8 -*-
#
# Copyright (C)2005-2009 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

import six


class Table(object):
    """Declare a table in a database schema."""

    def __init__(self, name, key=[]):
        self.name = name
        self.columns = []
        self.indices = []
        self.key = [key] if isinstance(key, six.string_types) else key

    def __getitem__(self, objs):
        self.columns = [o for o in objs if isinstance(o, Column)]
        self.indices = [o for o in objs if isinstance(o, Index)]
        return self

    def remove_columns(self, column_names):
        """Remove columns specified in the list or tuple `column_names`."""
        if not isinstance(column_names, (list, tuple)):
            column_names = [column_names]
        if any(c in column_names for c in self.key):
            self.key = []
        self.columns = [col for col in self.columns
                        if col.name not in column_names]
        self.indices = [idx for idx in self.indices
                        if all(c not in column_names for c in idx.columns)]


class Column(object):
    """Declare a table column in a database schema."""

    def __init__(self, name, type='text', size=None, key_size=None,
                 auto_increment=False):
        self.name = name
        self.type = type
        self.size = size
        self.key_size = key_size
        self.auto_increment = auto_increment


class Index(object):
    """Declare an index for a database schema."""

    def __init__(self, columns, unique=False):
        self.columns = columns
        self.unique = unique
