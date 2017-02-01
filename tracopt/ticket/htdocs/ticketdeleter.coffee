# -*- coding: utf-8 -*-
#
# Copyright (C) 2016 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

# Add ''Delete'' ticket action in ticket box and ticket comments.

# The script is added via the tracopt.ticket.deleter component.
#
# It uses the following Trac global variables:
#  - from add_script_data in tracopt.ticket.deleter: ui
#    (TODO: generalize this)
#  - from add_script_data in trac.web.chrome: form_token

$ = jQuery

captionedButton = (symbol, text) ->
  if ui.use_symbols then symbol else "#{symbol} #{text}"

deleteTicket = () ->
  $ """
    <form action="#" method="get">
     <div class="inlinebuttons">
      <input type="hidden" name="action" value="delete">
      <input type="submit" 
             value="#{captionedButton '–', _("Delete")}"
             title="#{_("Delete ticket")}"
             class="trac-delete">
      <input type="hidden" name="__FORM_TOKEN" value="#{form_token}">
     </div>
    </form>
  """

deleteComment = (c) ->
  # c.id == "trac-change-3-1347886395121000"
  #          0123456789012
  [cnum, cdate] = c.id.substr(12).split('-')
  $ """
    <form action="#" method="get">
     <div class="inlinebuttons">
      <input type="hidden" name="action" value="delete-comment">
      <input type="hidden" name="cnum", value="#{cnum}">
      <input type="hidden" name="cdate" value="#{cdate}">
      <input type="submit"
             value="#{captionedButton '–', _("Delete")}"
             title="#{_("Delete comment %(num)s", num: cnum)}"
             class="trac-delete">
      <input type="hidden" name="__FORM_TOKEN" value="#{form_token}">
     </div>
    </form>
  """


$(document).ready () ->
  # Insert "Delete" buttons for ticket description and each comment
  $('#ticket .description h3').after(deleteTicket())
  $('#changelog div.change').each () ->
    $('.trac-ticket-buttons', this).prepend deleteComment this
