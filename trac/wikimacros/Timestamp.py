"""Inserts the current time (in seconds) into the wiki page."""

import time
def execute(hdf, txt, env):
    t = time.localtime()
    return "<b>%s</b>" % time.strftime('%c', t)
