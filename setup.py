#!/usr/bin/env python

import os
import glob
from distutils.core import setup
import trac

VERSION = str(trac.__version__)
URL = trac.__url__
LICENSE = trac.__license__

setup(name="trac",
      description="",
      version=VERSION,
      license=LICENSE,
      url=URL,
      packages=['trac'],
      data_files=[('share/trac/templates', glob.glob('templates/*')),
                  ('share/trac/htdocs', glob.glob('htdocs/*'))],
      scripts=[os.path.join('scripts', 'trac-admin')])

