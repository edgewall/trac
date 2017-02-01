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
#  - from add_script_data in tracopt.ticket.clone: baseurl, ui
#    (TODO: generalize this)
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
    <form action="#{baseurl}/newticket" method="post">
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
      "id", "summary", "description", "status", "resolution"
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
        _("Copied from [%(source)s]:\n----\n%(description)s",
          source: "ticket:#{old_values.id}#comment:#{c.cnum}",
          description: c.comment)

      btns.prepend cform


$(document).ready () ->
  # clone from description
  clone = createCloneAction _("Create a copy of this ticket")
  addField clone, 'summary',
    _("(%(summary)s (cloned)", summary: old_values.summary)
  addField clone, 'description',
    _("Cloned from #%(id)s:\n----\n%(description)s",
      id: old_values.id, description: old_values.description)
  $('#ticket .description .searchable').before(clone)
  # clone from comment
  if old_values? and changes?
    addCloneFromComments (c for c in changes when c.cnum? and
                          c.comment and c.permanent)
