import time
def execute(hdf, txt, env, href):
    t = time.localtime()
    return "<b>%s</b>" % time.strftime('%c', t)
