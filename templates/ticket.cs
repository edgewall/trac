<?cs include "header.cs" ?>
<?cs include "macros.cs" ?>
<div id="page-content">
<div id="subheader-links">
<br />
</div>

 <div id="main">
  <div id="main-content">

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

<h1 id="tkt-hdr">Ticket #<?cs var:ticket.id ?><?cs var:status ?></h1>

<div id="tkt-main">

<table id="tkt-ticket">
 <tr>
  <td colspan="5">
   <div id="tkt-date"><?cs var:ticket.opened ?></div>
   <h2 id="tkt-summary">#<?cs var:ticket.id ?> : <?cs var:ticket.summary ?></h2>
  </td>
 </tr>
 <tr><td colspan="5" class="tkt-row-sep"><hr class="hide"/></td></tr>
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
  <td colspan="2">&nbsp;</td>
 </tr>
 <tr>
   <td colspan="2" class="tkt-row-sep"></td>
   <td colspan="1" class="tkt-row-sep-vert"></td>
   <td colspan="2" class="tkt-row-sep"> </td>
 </tr>
 <tr>
  <td colspan="5" id="tkt-descr">
   <hr class="hide" />
   <h3 id="tkt-descr-hdr">Description by <?cs var:ticket.reporter ?>:</h3>
   <?cs var:ticket.description ?>
   <hr class="hide"/>
  </td>
 </tr>
</table>

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

<h3>Add/Change Information</h3>
<form action="<?cs var:cgi_location ?>" method="post">
 <table id="nt-upper">
  <tr>
   <td class="nt-label">Opened:</td>
   <td class="nt-widget">
    <input type="hidden" name="mode" value="ticket" />
    <input type="hidden" name="id"   value="<?cs var:ticket.id ?>" />
    <?cs var:ticket.opened ?>
   </td>
   <td class="nt-prop-sep">&nbsp;</td>
   <td class="nt-label">Editor:</td>
   <td class="nt-widget">
    <input type="text" name="reporter" value="<?cs var:trac.authname ?>" />
   </td>
  </tr>
  <tr>
   <td class="nt-label">Version:</td>
   <td class="nt-widget">
    <?cs call:hdf_select(ticket.versions, "version", ticket.version) ?>
   </td>
   <td class="nt-prop-sep">&nbsp;</td>
   <td class="nt-label">Priority:</td>
   <td class="nt-widget">
    <?cs call:hdf_select(enums.priority, "priority", ticket.priority) ?>
   </td>
  </tr>
  <tr>
   <td class="nt-label">Component:</td>
   <td class="nt-widget">
    <?cs call:hdf_select(ticket.components, "component", ticket.component) ?>
   </td>
   <td class="nt-prop-sep">&nbsp;</td>
   <td class="nt-label">Milestone:</td>
   <td class="nt-widget">
    <?cs call:hdf_select(ticket.milestones, "milestone", ticket.milestone) ?>
   </td>
  </tr>
  <tr>
   <td class="nt-label">Severity:</td>
   <td class="nt-widget">
    <?cs call:hdf_select(enums.severity, "severity", ticket.severity) ?>
   </td>
   <td class="nt-prop-sep">&nbsp;</td>
   <td class="nt-label">Assigned to:</td>
   <td class="nt-widget"><?cs var:ticket.owner ?></td>
  </tr>
  <tr>
   <td class="nt-label">Status:</td>
   <td class="nt-widget"><?cs var:ticket.status ?></td>
   <td class="nt-prop-sep">&nbsp;</td>
   <td class="nt-label"></td><td class="nt-widget"></td>
  </tr>
  <?cs if:ticket.resolution ?>
  <tr>
   <td class="nt-label">Resolution:</td>
   <td class="nt-widget"><?cs var:ticket.resolution ?></td>
   <td class="nt-prop-sep">&nbsp;</td>
   <td class="nt-label"></td><td class="nt-widget"></td>
  </tr>
  <?cs /if ?>
  <tr>
   <td colspan="2" class="nt-row-sep">&nbsp;</td>
   <td class="nt-prop-sep">&nbsp;</td>
   <td colspan="2" class="nt-row-sep">&nbsp</td>
  </tr>
 </table>

<table id="nt-lower">
 <tr>
  <td class="nt-label">Cc:</td>
  <td class="nt-widget">
   <input type="text" name="cc" value="<?cs var:ticket.cc ?>" size="66" />
  </td>
 </tr>
 <tr>
  <td class="nt-label"><a href="<?cs var:ticket.url ?>">URL</a>:</td>
  <td class="nt-widget">
   <input type="text" name="url" value="<?cs var:ticket.url ?>" size="66" />
  </td>
 </tr>
 <tr>
  <td class="nt-label">Summary:</td>
  <td class="nt-widget">
   <input type="text" name="summary" 
          value="<?cs var:ticket.summary ?>" size="66" />
  </td>
 </tr>
 <tr><td colspan="2" id="nt-row-sep">&nbsp;</td></tr>
 <tr>
  <td colspan="2" id="nt-descr">Add Comments:</td>
 </tr>
 <tr>
  <td colspan="2" class="nt-widget">
   <textarea name="comment" rows="12" cols="80"></textarea>
  </td>
 </tr>
 <tr>
  <td colspan="2" id="tkt-submit">
   <input type="radio" name="action" value="leave" checked="checked" />
    &nbsp;leave as <?cs var:ticket.status ?><br />
   <?cs if $ticket.status == "new" ?>
    <input type="radio" name="action" value="accept" />
     &nbsp;accept ticket<br />
   <?cs /if ?>
   <?cs if $ticket.status == "closed" ?>
    <input type="radio" name="action" value="reopen" />
     &nbsp;reopen ticket<br />
   <?cs /if ?>
   <?cs if $ticket.status == "new" || $ticket.status == "assigned" || $ticket.status == "reopened" ?>
    <input type="radio" name="action" value="resolve" />
     &nbsp;resolve as: 
     <select name="resolve_resolution">
      <option selected="selected">fixed</option>
      <option>invalid</option>
      <option>wontfix</option>
      <option>duplicate</option>
      <option>worksforme</option>
     </select><br />
    <input type="radio" name="action" value="reassign" />
    &nbsp;reassign ticket to:
    &nbsp;<input type="text" name="reassign_owner" 
          value="<?cs var:ticket.owner ?>" />
   <?cs /if ?>
   <br />
   <input type="submit" value="Submit" /> 
  </td>
 </tr>
 <tr>
  <td colspan="2" id="tkt-submit">
<div id="help">
<strong>Note:</strong> See <a href="<?cs var:$trac.href.wiki
?>TracTickets">TracTickets</a> for help on editing tickets.
</div>
  </td>
 </tr>
</table>
</form>
</div> <!-- #tkt-main -->


 </div>
</div>
</div>
<?cs include:"footer.cs"?>

