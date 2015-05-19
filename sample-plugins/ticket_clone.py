from trac.core import *
from trac.web.api import ITemplateStreamFilter

from genshi.builder import tag
from genshi.filters import Transformer

revision = "$Rev$"
url = "$URL$"

class SimpleTicketCloneButton(Component):
    """Add a 'Clone' button to the ticket box. 
    
    This button is located next to the 'Reply' to description button,
    and pressing it will send a request for creating a new ticket
    which will be based on the cloned one.
    """
       
    implements(ITemplateStreamFilter)

    # ITemplateStreamFilter methods

    def filter_stream(self, req, method, filename, stream, data):
        if filename == 'ticket.html':
            ticket = data.get('ticket')
            if ticket and ticket.exists and \
                    'TICKET_ADMIN' in req.perm(ticket.resource):
                filter = Transformer('//h3[@id="comment:description"]')
                return stream | filter.after(self._clone_form(req, ticket, data))
        return stream

    def _clone_form(self, req, ticket, data):
        fields = {}
        for f in data.get('fields', []):
            name = f['name']
            if name == 'summary':
                fields['summary'] = ticket['summary'] + " (cloned)"
            elif name == 'description':
                fields['description'] = "Cloned from #%s: \n----\n%s" % \
                    (ticket.id, ticket['description'])
            else:
                fields[name] = ticket[name]
        return tag.form(
            tag.div(
                tag.input(type="submit", name="clone", value="Clone",
                    title="Create a copy of this ticket"),
                [tag.input(type="hidden", name='field_'+n, value=v) for n, v in
                    fields.items()],
                tag.input(type="hidden", name='preview', value=''),
                class_="inlinebuttons"),
            method="post", action=req.href.newticket())

