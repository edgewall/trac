<?cs include "header.cs" ?>
<?cs include "macros.cs" ?>
<div id="page-content">
<h2 class="hide">Ticket Navigation</h2>
<ul class="subheader-links">
 <li class="last"><a href="#edit">Add/Change Info</a></li>
</ul>

 <div id="main">
  <div id="main-content">
   <div id="searchable">

<?cs if:ticket.status == 'closed' ?>
 <?cs set:status = ' (Closed: ' + $ticket.resolution + ')' ?>
<?cs elif:ticket.status == 'new' ?>
<?cs else ?>
 <?cs set:status = ' (' + ticket.status + ')' ?>
<?cs /if ?>

<?cs def:ticketprop(label, value) ?>
 <td class="tkt-label"><b><?cs var:$label ?>:</b></td>
 <td class="tkt-val">
  <?cs if:$value ?><i><?cs var:$value ?></i><?cs else ?>&nbsp;<?cs /if ?>
 </td>
 <?cs if numprops % #2 ?>
  </tr><tr>
 <?cs else ?>
  <td class="tkt-prop-sep">&nbsp;</td>
 <?cs /if ?>
 <?cs set numprops = $numprops + #1 ?>
<?cs /def ?>

<div id="tkt-main">
<div id="tkt-ticket">
 <div id="tkt-date"><?cs var:ticket.opened ?></div>
<h1 id="tkt-hdr">Ticket #<?cs var:ticket.id ?><?cs var:status ?><br />
 <span class="hide">-</span> <span id="tkt-subhdr"><?cs var:ticket.summary ?></span></h1>
 <hr class="hide" />
 <table style="width: 100%">
  <tr>
   <?cs call:ticketprop("Priority", ticket.priority) ?>
   <?cs call:ticketprop("Reporter", ticket.reporter) ?>
   <?cs call:ticketprop("Severity", ticket.severity) ?>
   <?cs if ticket.status == "assigned"?>
    <?cs call:ticketprop("Assigned to", ticket.owner + " (accepted)") ?>
   <?cs else ?>
    <?cs call:ticketprop("Assigned to", ticket.owner) ?>
   <?cs /if ?>
   <?cs call:ticketprop("Component", ticket.component) ?>
   <?cs call:ticketprop("Status", ticket.status) ?>
   <?cs call:ticketprop("Version", ticket.version) ?>
   <?cs call:ticketprop("Resolution", ticket.resolution) ?>
   <?cs call:ticketprop("Milestone", ticket.milestone) ?>
   <?cs call:ticketprop("Keywords", ticket.keywords) ?>
  </tr>
 </table>
<?cs if ticket.custom.0.name ?>
 <hr class="hide" />
 <h3 id="tkt-custom-hdr">Custom Properties</h3>
 <table style="width: 100%">
  <tr>
  <?cs each c=ticket.custom ?>
   <?cs call:ticketprop(c.label, c.value) ?>
  <?cs /each ?>
  </tr>
 </table><?cs /if ?>
 <hr class="hide" />
 <h3 id="tkt-descr-hdr">Description by <?cs var:ticket.reporter ?>:</h3>
    <?cs var:ticket.description ?>
 <hr class="hide"/>
</div>

<?cs if trac.acl.TICKET_MODIFY || ticket.attachments.0.name ?>
 <h2 id="tkt-changes-hdr">Attachments</h2>
 <?cs if ticket.attachments.0.name ?>
  <div id="tkt-changes">
   <ul class="tkt-chg-list">
    <?cs each:a = ticket.attachments ?>
     <li class="tkt-chg-change"><a href="<?cs var:a.href ?>">
      <?cs var:a.name ?></a> (<?cs var:a.size ?>) -
      <?cs var:a.descr ?>,
      added by <?cs var:a.author ?> on <?cs var:a.time ?>.</li>
    <?cs /each ?>
   </ul>
 <?cs /if ?>
 <?cs if trac.acl.TICKET_MODIFY ?>
  <form method="get" action="<?cs var:cgi_location?>/attachment/ticket/<?cs var:ticket.id ?>"><div>
   <input type="submit" value="Attach File" />
   </div></form>
 <?cs /if ?>
 <?cs if ticket.attachments.0.name ?>
  </div>
 <?cs /if ?>
<?cs /if ?>

<?cs if ticket.changes.0.time ?>
  <h2 id="tkt-changes-hdr">Changelog</h2>
  <div id="tkt-changes">
    <?cs set:numchanges = 0 ?>
    <?cs set:comment = "" ?>
    <?cs set:curr_time = "" ?>
    <?cs set:curr_author = "" ?>
    <?cs each:item = ticket.changes ?>
      <?cs set:numchanges = #numchanges + 1 ?>
      <?cs if $item.time != $curr_time || $item.author != $curr_author ?>
        <?cs if $comment != "" ?>
          <li class="tkt-chg-change">
            <h4 class="tkt-chg-comment-hdr">Comment:</h4>
            <div  class="tkt-chg-comment"><?cs var:$comment ?></div>
            <?cs set:comment = "" ?>
          </li>
        <?cs /if ?>
        <?cs set:curr_time = $item.time ?>
        <?cs set:curr_author = $item.author ?>
        <?cs if:#numchanges > 1 ?>
          </ul>
          <hr class="hide"/>
        <?cs /if ?>
        <h3 class="tkt-chg-mod">
          <a name="<?cs var:#numchanges ?>"><?cs var:item.date ?> : Modified by <?cs var:curr_author ?></a>
        </h3>
        <ul class="tkt-chg-list">
      <?cs /if ?>
      <?cs if $item.field == "comment" ?>
      <?cs set:$comment = $item.new ?> 
      <?cs elif $item.new == "" ?>
        <li class="tkt-chg-change">
           cleared <b><?cs var:item.field?></b>
        </li>
      <?cs elif $item.field == "attachment" ?>
        <li class="tkt-chg-change">
           <b>Attachment</b> added: <?cs var:item.new ?>
        </li>
      <?cs elif $item.field == "description" ?>
        <li class="tkt-chg-change">
           <b><?cs var:item.field ?></b> changed.
        </li>
      <?cs elif $item.old == "" ?>
        <li class="tkt-chg-change">
          <b><?cs var:item.field ?></b> set to <b><?cs var:item.new ?></b>
        </li>
      <?cs else ?>
        <li class="tkt-chg-change">
           <b><?cs var:item.field ?></b> changed from
           <b><?cs var:item.old ?></b> to
           <b><?cs var:item.new ?></b>
        </li>
      <?cs /if ?>
    <?cs /each ?>
    <?cs if $comment != "" ?>
       <li class="tkt-chg-change">
         <h4 class="tkt-chg-comment-hdr">Comment:</h4>
         <div  class="tkt-chg-comment"><?cs var:$comment ?></div>
       </li>
     <?cs /if ?>
    </ul>
  </div>
<?cs /if ?>

<br /><hr />


<h3><a name="edit"
onfocus="document.getElementById('comment').focus()">Add/Change
#<?cs var:ticket.id ?> (<?cs var:ticket.summary ?>)</a></h3>
<form action="<?cs var:cgi_location ?>#preview" method="post" enctype="multipart/form-data">
  <div class="tkt-prop">
   <input type="hidden" name="mode" value="ticket" />
   <input type="hidden" name="id"   value="<?cs var:ticket.id ?>" />
   <label for="reporter">Your email or username:</label><br />
    <input type="text" id="reporter" name="reporter" class="textwidget" size="40"
           value="<?cs var:ticket.reporter_id ?>" /><br />
  </div>
  <div class="tkt-prop">
  <label for="comment">Add Comment (You may use 
      <a tabindex="42" href="<?cs var:$trac.href.wiki ?>/WikiFormatting">WikiFormatting</a> here):</label><br />

  <textarea id="comment" name="comment" class="textwidget"
            rows="10" cols="78" style="width: 97%; max-width: 694px"><?cs var:ticket.comment ?></textarea>
   <?cs if ticket.comment_preview ?>
     <a name="preview" />
     <fieldset>
     <legend>Comment Preview</legend>
       <?cs var:ticket.comment_preview ?>
     </fieldset>
   <?cs /if ?>
  </div>

 <fieldset>
   <legend>Change Properties</legend>
 <div id="nt-props"  style="padding: .5em">
<div style="margin-bottom: 1em">
<label for="summary" class="nt-label">Summary:</label>
<input id="summary" type="text" name="summary" class="textwidget" size="80"
       value="<?cs var:ticket.summary ?>" />
<?cs if $trac.acl.TICKET_ADMIN ?>
  <br />
  <label for="description" class="nt-label">Description:</label>
  <textarea id="description" name="description" class="textwidget"
            rows="10" cols="68"><?cs var:ticket.description.raw ?></textarea>
<?cs /if ?>
</div>
  <div id="nt-left">
   <label for="component" class="nt-label">Component:</label>
   <?cs call:hdf_select(ticket.components, "component", ticket.component) ?>
   <br />
   <label for="version" class="nt-label">Version:</label>
   <?cs call:hdf_select(ticket.versions, "version", ticket.version) ?>
   <br />
   <label for="severity" class="nt-label">Severity:</label>
   <?cs call:hdf_select(enums.severity, "severity", ticket.severity) ?>
   <br />
   <label for="keywords" class="nt-label">Keywords:</label>
   <input type="text" id="keywords" name="keywords" size="25" class="textwidget" 
          value="<?cs var:ticket.keywords ?>" />
   <br />&nbsp;
  </div>
 <div  id="nt-right" style="">
  <label for="priority" class="nt-label">Priority:</label>
  <?cs call:hdf_select(enums.priority, "priority", ticket.priority) ?>
  <br />
  <label for="milestone" class="nt-label">Milestone:</label>
  <?cs call:hdf_select(ticket.milestones, "milestone", ticket.milestone) ?>
  <br />
  <span class="nt-label">Assigned to:</span>
  <?cs var:ticket.owner ?>
  <br />
  <label for="cc" class="nt-label">Cc:</label>
   <input type="text" id="cc" name="cc" class="textwidget"
          value="<?cs var:ticket.cc ?>" size="35" />
  </div>
 </div>

<?cs call:ticket_custom_props(ticket) ?>

  </fieldset>


 <div id="tkt-submit">
  <fieldset>
   <legend>Action</legend>
  <input type="radio" id="leave" name="action" value="leave" checked="checked" />
   &nbsp;<label for="leave">leave as <?cs var:ticket.status ?></label><br />
   <?cs if $ticket.status == "new" ?>
    <input type="radio" id="accept" name="action" value="accept" />
     &nbsp;<label for="accept">accept ticket</label><br />
   <?cs /if ?>
   <?cs if $ticket.status == "closed" ?>
    <input type="radio" id="reopen" name="action" value="reopen" />
     &nbsp;<label for="reopen">reopen ticket</label><br />
   <?cs /if ?>
   <?cs if $ticket.status == "new" || $ticket.status == "assigned" || $ticket.status == "reopened" ?>
    <input type="radio" id="resolve" name="action" value="resolve" />
     &nbsp;<label for="resolve">resolve as:</label>
     <select name="resolve_resolution">
      <option selected="selected">fixed</option>
      <option>invalid</option>
      <option>wontfix</option>
      <option>duplicate</option>
      <option>worksforme</option>
     </select><br />
    <input type="radio" id="reassign" name="action" value="reassign" />
    &nbsp;<label for="reassign">reassign ticket to:</label>
    &nbsp;<input type="text" id="reassign_owner" name="reassign_owner" 
           class="textwidget" value="<?cs var:trac.authname ?>" />
   <?cs /if ?>
   </fieldset>

  <div id="nt-buttons" style="clear: both">
   <input type="reset" value="Reset" />&nbsp;
   <input type="submit" name="preview" value="Preview" />&nbsp;
   <input type="submit" value="Submit changes" /> 
  </div>
 </div>


</form>



</div> <!-- #tkt-main -->

</div>
 </div>
</div>
</div>
<?cs include:"footer.cs"?>

