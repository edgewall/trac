#!/usr/bin/env python

from distutils.core import setup
import svntrac

VERSION = str(svntrac.__version__)
URL = svntrac.__url__
LICENSE = svntrac.__license__

setup(name="svntrac",
      description="",
      version=VERSION,
      license=LICENSE,
      url=URL,
      packages=['svntrac'])

