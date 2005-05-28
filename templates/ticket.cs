<?cs include "header.cs" ?>
<?cs include "macros.cs" ?>

<div id="ctxtnav" class="nav">
 <h2>Ticket Navigation</h2><?cs
 with:links = chrome.links ?>
  <ul><?cs
   if:len(links.prev) ?>
    <li class="first<?cs if:!len(links.up) && !len(links.next) ?> last<?cs /if ?>">
     &larr; <a href="<?cs var:links.prev.0.href ?>" title="<?cs
       var:links.prev.0.title ?>">Previous Ticket</a>
    </li><?cs
   /if ?><?cs
   if:len(links.up) ?>
    <li class="<?cs if:!len(links.prev) ?>first<?cs /if ?><?cs
                    if:!len(links.next) ?> last<?cs /if ?>">
     <a href="<?cs var:links.up.0.href ?>" title="<?cs
       var:links.up.0.title ?>">Back to Query</a>
    </li><?cs
   /if ?><?cs
   if:len(links.next) ?>
    <li class="<?cs if:!len(links.prev) && !len(links.up) ?>first <?cs /if ?>last">
     <a href="<?cs var:links.next.0.href ?>" title="<?cs
       var:links.next.0.title ?>">Next Ticket</a> &rarr;
    </li><?cs
   /if ?>
  </ul><?cs
 /with ?>
</div>

<div id="content" class="ticket">

 <h1>Ticket #<?cs var:ticket.id ?> <?cs
 if:ticket.type ?> - <?cs var:ticket.type ?> <?cs /if ?><?cs
 if:ticket.resolution ?>(<?cs var:ticket.status ?>: <?cs var:ticket.resolution ?>)<?cs
 elif:ticket.status != 'new' ?>(<?cs var:ticket.status ?>)<?cs
 /if ?></h1>

 <div id="searchable">
 <?cs def:ticketprop(label, name, value, fullrow) ?>
  <th id="h_<?cs var:name ?>"><?cs var:label ?>:</th>
  <td headers="h_<?cs var:name ?>"<?cs if:fullrow ?> colspan="3"<?cs /if ?>><?cs
   var:value ?></td><?cs 
  if:numprops % #2 && !last_prop || fullrow ?></tr><tr><?cs /if ?><?cs
  set numprops = numprops + #1 - fullrow ?><?cs
 /def ?>

<div id="ticket">
 <div class="date">
  <p title="<?cs var:ticket.opened ?>">Opened <?cs var:ticket.opened_delta ?> ago</p><?cs
  if:ticket.lastmod ?>
   <p title="<?cs var:ticket.lastmod ?>">Last modified <?cs var:ticket.lastmod_delta ?> ago</p>
  <?cs /if ?>
 </div>
 <h2 class="summary"><?cs var:ticket.summary ?></h2>
 <table class="properties"><tr><?cs
  if:len(enums.priority) ?><?cs
   call:ticketprop("Priority", "priority", ticket.priority, 0) ?><?cs
  /if ?><?cs
  call:ticketprop("Reporter", "reporter", ticket.reporter, 0) ?><?cs
  if:len(enums.severity) ?><?cs
   call:ticketprop("Severity", "severity", ticket.severity, 0) ?><?cs
  /if ?><?cs
  if ticket.status == "assigned"?><?cs
   call:ticketprop("Assigned to", "assignee", ticket.owner + " (accepted)", 0) ?><?cs
  else ?><?cs
   call:ticketprop("Assigned to", "assignee", ticket.owner, 0) ?><?cs
  /if ?><?cs
  if:len(ticket.components) ?><?cs
   call:ticketprop("Component", "component", ticket.component, 0) ?><?cs
  /if ?><?cs
  call:ticketprop("Status", "status", ticket.status, 0) ?><?cs
  if:len(ticket.versions) ?><?cs
   call:ticketprop("Version", "version", ticket.version, 0) ?><?cs
  /if ?><?cs
  call:ticketprop("Resolution", "resolution", ticket.resolution, 0) ?><?cs
  if:len(ticket.milestones) ?><?cs
   call:ticketprop("Milestone", "milestone", ticket.milestone, 0) ?><?cs
  /if ?><?cs
  set:last_prop = #1 ?><?cs
  call:ticketprop("Keywords", "keywords", ticket.keywords, 0) ?><?cs
  set:last_prop = #0 ?>
 </tr></table><?cs if:ticket.custom.0.name ?>
 <table class="custom properties"><tr><?cs each:prop = ticket.custom ?><?cs
   if:name(prop) == len(ticket.custom) - 1 ?><?cs set:last_prop = #1 ?><?cs
   /if ?><?cs
   if:prop.type == "textarea" ?><?cs
    call:ticketprop(prop.label, prop.name, prop.value, 1) ?><?cs
   else ?><?cs
    call:ticketprop(prop.label, prop.name, prop.value, 0) ?><?cs
   /if?><?cs
  /each ?>
 </tr></table><?cs /if ?>
 <?cs if:ticket.description ?><div class="description">
  <?cs var:ticket.description.formatted ?>
 </div><?cs /if ?>
</div>

<?cs if:ticket.attach_href || len(ticket.attachments) ?>
<h2>Attachments</h2><?cs
 if:len(ticket.attachments) ?><div id="attachments">
  <dl class="attachments"><?cs each:attachment = ticket.attachments ?>
   <dt><a href="<?cs var:attachment.href ?>" title="View attachment"><?cs
   var:attachment.filename ?></a> (<?cs var:attachment.size ?>) - added by <em><?cs
   var:attachment.author ?></em> on <?cs
   var:attachment.time ?>.</dt><?cs
   if:attachment.description ?>
    <dd><?cs var:attachment.description ?></dd><?cs
   /if ?><?cs
  /each ?></dl><?cs
 /if ?><?cs
 if:ticket.attach_href ?>
  <form method="get" action="<?cs var:ticket.attach_href ?>"><div>
   <input type="hidden" name="action" value="new" />
   <input type="submit" value="Attach File" />
  </div></form><?cs
 /if ?><?cs if:len(ticket.attachments) ?></div><?cs /if ?>
<?cs /if ?>

<?cs if:len(ticket.changes) ?><h2>Change History</h2>
<div id="changelog"><?cs
 each:change = ticket.changes ?>
  <h3 id="change_<?cs var:name(change) ?>" class="change"><?cs
   var:change.date ?>: Modified by <?cs var:change.author ?></h3><?cs
  if:len(change.fields) ?>
   <ul class="changes"><?cs
   each:field = change.fields ?>
    <li><strong><?cs var:name(field) ?></strong> <?cs
    if:name(field) == 'attachment' ?><em><?cs var:field.new ?></em> added<?cs
    elif:field.old && field.new ?>changed from <em><?cs
     var:field.old ?></em> to <em><?cs var:field.new ?></em><?cs
    elif:!field.old && field.new ?>set to <em><?cs var:field.new ?></em><?cs
    elif:field.old && !field.new ?>deleted<?cs
    else ?>changed<?cs
    /if ?>.</li>
    <?cs
   /each ?>
   </ul><?cs
  /if ?>
  <div class="comment"><?cs var:change.comment ?></div><?cs
 /each ?></div><?cs
/if ?>

<?cs if:trac.acl.TICKET_CHGPROP || trac.acl.TICKET_APPEND ?>
<form action="<?cs var:ticket.href ?>#preview" method="post">
 <hr />
 <h3><a name="edit" onfocus="document.getElementById('comment').focus()">Add/Change #<?cs
   var:ticket.id ?> (<?cs var:ticket.summary ?>)</a></h3>
 <div class="field">
  <label for="author">Your email or username:</label><br />
  <input type="text" id="author" name="author" size="40"
    value="<?cs var:ticket.reporter_id ?>" /><br />
 </div>
 <div class="field">
  <fieldset class="iefix">
   <label for="comment">Comment (you may use <a tabindex="42" href="<?cs
     var:trac.href.wiki ?>/WikiFormatting">WikiFormatting</a> here):</label><br />
   <p><textarea id="comment" name="comment" class="wikitext" rows="10" cols="78"><?cs
     var:ticket.comment ?></textarea></p>
  </fieldset><?cs
  if ticket.comment_preview ?>
   <fieldset id="preview">
    <legend>Comment Preview</legend>
    <?cs var:ticket.comment_preview ?>
   </fieldset><?cs
  /if ?>
 </div>

 <?cs if:trac.acl.TICKET_CHGPROP ?><fieldset id="properties">
  <legend>Change Properties</legend>
  <div class="main">
   <label for="summary">Summary:</label>
   <input id="summary" type="text" name="summary" size="70" value="<?cs
     var:ticket.summary ?>" />
   <br /><?cs
   call:labelled_hdf_select('Type:', enums.ticket_type, "type", ticket.type, 0) ?><?cs
   if:trac.acl.TICKET_ADMIN ?>
    <label for="description">Description:</label>
    <div style="float: left">
     <textarea id="description" name="description" class="wikitext" rows="10" cols="68"><?cs
        var:ticket.description ?></textarea>
    </div>
    <br style="clear: left" />
    <label for="reporter">Reporter:</label>
    <input id="reporter" type="text" name="reporter" size="70"
           value="<?cs var:ticket.reporter ?>" /><?cs
   /if ?>
  </div>
  <div class="col1"><?cs
   call:labelled_hdf_select("Component:", ticket.components, "component", ticket.component, 0) ?><?cs
   call:labelled_hdf_select("Version:", ticket.versions, "version", ticket.version, 1) ?><?cs 
   call:labelled_hdf_select("Severity:", enums.severity, "severity", ticket.severity, 0) ?>
   <label for="keywords">Keywords:</label>
   <input type="text" id="keywords" name="keywords" size="20"
       value="<?cs var:ticket.keywords ?>" />
  </div>
  <div class="col2"><?cs
   call:labelled_hdf_select("Priority:", enums.priority, "priority", ticket.priority, 0) ?><?cs
   call:labelled_hdf_select("Milestone:", ticket.milestones, "milestone", ticket.milestone, 1) ?>
   <label for="owner">Assigned to:</label>
   <input type="text" id="owner" name="owner" size="20" value="<?cs
     var:ticket.owner ?>" disabled="disabled" /><br />
   <label for="cc">Cc:</label>
   <input type="text" id="cc" name="cc" size="30" value="<?cs var:ticket.cc ?>" />
  </div>
  <?cs if:len(ticket.custom) ?><div class="custom">
   <?cs call:ticket_custom_props(ticket) ?>
  </div><?cs /if ?>
 </fieldset><?cs /if ?>

 <?cs if:ticket.actions.accept || ticket.actions.reopen ||
         ticket.actions.resolve || ticket.actions.reassign ?>
 <fieldset id="action">
  <legend>Action</legend><?cs
  if:!ticket.action ?><?cs set:ticket.action = 'leave' ?><?cs
  /if ?><?cs
  def:action_radio(id) ?>
   <input type="radio" id="<?cs var:id ?>" name="action" value="<?cs
     var:id ?>"<?cs if:ticket.action == id ?> checked="checked"<?cs
     /if ?> /><?cs
  /def ?>
  <?cs call:action_radio('leave') ?>
   <label for="leave">leave as <?cs var:ticket.status ?></label><br /><?cs
  if:ticket.actions.accept ?><?cs
   call:action_radio('accept') ?>
   <label for="accept">accept ticket</label><br /><?cs
  /if ?><?cs
  if:ticket.actions.reopen ?><?cs
   call:action_radio('reopen') ?>
   <label for="reopen">reopen ticket</label><br /><?cs
  /if ?><?cs
  if:ticket.actions.resolve ?><?cs
   call:action_radio('resolve') ?>
   <label for="resolve">resolve</label>
   <label for="resolve_resolution">as:</label>
   <?cs call:hdf_select(enums.resolution, "resolve_resolution",
                        ticket.resolve_resolution, 0) ?><br /><?cs
  /if ?><?cs
  if:ticket.actions.reassign ?><?cs
   call:action_radio('reassign') ?>
   <label for="reassign">reassign</label>
   <label>to:<?cs
   if:len(ticket.users) ?><?cs
    call:hdf_select(ticket.users, "reassign_owner", ticket.reassign_owner, 0) ?><?cs
   else ?>
    <input type="text" id="reassign_owner" name="reassign_owner" size="40" value="<?cs
      var:ticket.reassign_owner ?>" /><?cs
   /if ?></label><?cs
  /if ?><?cs
  if ticket.actions.resolve || ticket.actions.reassign ?>
   <script type="text/javascript"><?cs
    each:action = ticket.actions ?>
     var <?cs var:name(action) ?> = document.getElementById("<?cs var:name(action) ?>");<?cs
    /each ?>
     var updateActionFields = function() {
       <?cs if:ticket.actions.resolve ?> enableControl('resolve_resolution', resolve.checked);<?cs /if ?>
       <?cs if:ticket.actions.reassign ?> enableControl('reassign_owner', reassign.checked);<?cs /if ?>
     };
     addEvent(window, 'load', updateActionFields);<?cs
     each:action = ticket.actions ?>
      addEvent(<?cs var:name(action) ?>, 'click', updateActionFields);<?cs
     /each ?>
   </script><?cs
  /if ?>
 </fieldset><?cs
 else ?>
  <input type="hidden" name="action" value="leave" /><?cs
 /if ?>

 <script type="text/javascript" src="<?cs
   var:htdocs_location ?>js/wikitoolbar.js"></script>

 <div class="buttons">
  <input type="submit" name="preview" value="Preview" />&nbsp;
  <input type="submit" value="Submit changes" />
 </div>
</form>
<?cs /if ?>

 </div>
</div>
<?cs include "footer.cs"?>
