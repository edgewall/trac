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

# Add ''Clone'' ticket action in ticket box and ticket comments.

# The script is added via the tracopt.ticket.clone component.
#
# It uses the following Trac global variables:
#  - from add_script_data in tracopt.ticket.clone: newticket_href, ui
#    (TODO: generalize this, have an href() js utility function)
#  - from add_script_data in trac.web.chrome: form_token
#  - from add_script_data in trac.ticket.web_ui:
#     * old_values: {name: value} for each field of the current ticket
#     * changes: list of objects containing the following properties,
#       {author, date, cnum, comment, comment_history, fields, permanent}

$ = jQuery

captionedButton = (symbol, text) ->
  if ui.use_symbols then symbol else "#{symbol} #{text}"

addField = (form, name, value) ->
  value = if value? then $.htmlEscape value else ''
  form.append $ """
    <input type="hidden" name="field_#{name}" value="#{value}">
  """

createCloneAction = (title) ->
  # the action needs to be wrapped in a <form>, as we want a POST
  form = $ """
    <form action="#{newticket_href}" method="post">
     <div class="inlinebuttons">
      <input type="submit" name="clone"
             value="#{captionedButton '+', _('Clone')}"
             title="#{title}">
      <input type="hidden" name="__FORM_TOKEN" value="#{form_token}">
      <input type="hidden" name="preview" value="">
     </div>
    </form>
  """
  # from ticket's old values, prefill most of the fields for new ticket
  for name, oldvalue of old_values
    addField form, name, oldvalue if name not in [
      "id", "summary", "description", "status", "resolution", "reporter"
    ]
  form


addCloneFromComments = (changes) ->
  form = createCloneAction _("Create a new ticket from this comment")
  # for each comment, retrieve comment number and add specific form
  for c in changes
    btns = $("#trac-change-#{c.cnum}-#{c.date} .trac-ticket-buttons")
    if btns.length
      # clone a specific form for this comment, as we need 2 specific fields
      cform = form.clone()

      addField cform, 'summary',
        _("(part of #%(ticketid)s) %(summary)s",
          ticketid: old_values.id, summary: old_values.summary)
      addField cform, 'description',
        _("Copied from [%(source)s]:\n%(description)s",
          source: "ticket:#{old_values.id}#comment:#{c.cnum}",
          description: quoteText(c.comment))

      insertNearReplyToComment c.cnum, cform


$(document).ready () ->
  # clone from description
  clone = createCloneAction _("Create a copy of this ticket")
  addField clone, 'summary',
    _("%(summary)s (cloned)", summary: old_values.summary)
  addField clone, 'description',
    _("Cloned from #%(id)s:\n%(description)s",
      id: old_values.id,
      description: quoteText(old_values.description))
  insertNearReplyToDescription clone
  # clone from comment
  if old_values? and changes?
    addCloneFromComments (c for c in changes when c.cnum? and
                          c.comment and c.permanent)


quoteText = (text) ->
  if text
    length = text.length
    pattern = /\r\n|[\r\n\u000b\u000c\u001c\u001d\u001e\u0085\u2028\u2029]/g
    repl = (match, offset) ->
      if match.length + offset != length then '\n> ' else ''
    '> ' + text.replace(pattern, repl) + '\n'
  else
    return ''
