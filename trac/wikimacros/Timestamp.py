import time
def execute(hdf, args):
    t = time.localtime()
    return "<b>%s</b>" % time.strftime('%c', t)
