# Hint: Use '0' precedence if you want to override SilverCity
supported_types = [
    (4, 'text/x-php', 'php'),
    (4, 'application/x-httpd-php'),
    (4, 'application/x-httpd-php4'),
    (4, 'application/x-httpd-php1'),
    ]

from enscript import Deuglifier
from trac.util import NaivePopen, Deuglifier


class PhpDeuglifier(Deuglifier):

    def rules(cls):
        return [
            r'(?P<comment><font color="#FF8000">)',
            r'(?P<keyword><font color="#5F9EA0">)',
            r'(?P<string><font color="#DD0000">)',
            r'(?P<func><font color="#007700">)',
            r'(?P<lang><font color="#0000BB">)',
            r'(?P<font><font.*?>)',
            r'(?P<endfont></font>)',
            ]
    rules = classmethod(rules)

def display(data, mimetype, filename, rev, env):
    php_s = 'php -s'
    try:
        np = NaivePopen(php_s, data, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % (php_s, np.errorlevel, np.err)
            raise Exception, err
        odata = np.out
        # Strip header
        beg = odata.find('<code>')
        odata = PhpDeuglifier().format(odata[beg:])
        return '<div class="code-block">' + odata + '</div>'
    except Exception, err:
        env.log.debug('PHP processor failed:' + err)

