from docutils.core import publish_string

def execute(hdf, text):
    html = publish_string(text, writer_name = 'html')
    return html[html.find('<body>')+6:html.find('</body>')].strip()

