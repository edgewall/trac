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

<h1 id="tkt-hdr">Ticket #<?cs var:ticket.id ?><?cs var:status ?></h1>

<div id="tkt-ticket">
  <span id="tkt-date">
    <?cs var:ticket.opened ?>
  </span>
  <h2 id="tkt-summary">
    #<?cs var:ticket.id ?> : <?cs var:ticket.summary ?>
  </h2>

<?cs def:ticketprop(label, value) ?>
  <div class="tkt-prop">
    <b class="tkt-label"><?cs var:label ?>:</b>&nbsp;
    <?cs if:value ?>
      <em class="tkt-val"><?cs var:value ?></em>
    <?cs else ?>
      <br />
    <?cs /if ?>
  </div>
<?cs /def ?>

<div id="tkt-left">
  <?cs call:ticketprop("Priority", ticket.priority) ?>
  <?cs call:ticketprop("Severity", ticket.severity) ?>
  <?cs call:ticketprop("Component", ticket.component) ?>
  <?cs call:ticketprop("Version", ticket.version) ?>
  <?cs call:ticketprop("Milestone", ticket.milestone) ?>
</div>
<div id="tkt-right">
  <?cs call:ticketprop("Reporter", ticket.reporter) ?>
  <?cs call:ticketprop("Assigned to", ticket.owner) ?>
  <?cs call:ticketprop("Status", ticket.status) ?>
  <?cs call:ticketprop("Resolution", ticket.resolution) ?>
</div>

<br style="clear: both" />

<div id="tkt-descr">
  <b>Description by <?cs var:ticket.reporter ?>:
  </b>
  <br />
  <?cs var:ticket.description ?>
</div>

</div> <!-- #tkt-ticket -->

<hr />

  <h2 id="tkt-changes-hdr">Changelog</h2>
  <div id="tkt-changes">
    <?cs set:numchanges = 0 ?>
    <?cs set:comment = "" ?>
    <?cs set:curr_date = "" ?>
    <?cs set:curr_author = "" ?>
    <?cs each:item = ticket.changes ?>
      <?cs set:numchanges = #numchanges + 1 ?>
      <?cs if $item.date != $curr_date || $item.author != $curr_author ?>
        <?cs if $comment != "" ?>
          <li class="tkt-chg-change">
            <h4 class="tkt-chg-comment-hdr">Comment:</h4>
            <div  class="tkt-chg-comment"><?cs var:$comment ?></div>
            <?cs set:comment = "" ?>
          </li>
        <?cs /if ?>
        <?cs set:curr_date = $item.date ?>
        <?cs set:curr_author = $item.author ?>
        <?cs if:#numchanges > 1 ?>
          </ul>
	<?cs /if ?>
        <h3 class="tkt-chg-mod">
	  <a name="<?cs var:#numchanges ?>"><?cs var:curr_date ?> : Modified by <?cs var:curr_author ?></a>
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
    </ul>
  </div>

<hr />

<form action="<?cs var:cgi_location ?>" method="post">
<h3>Add/Change Information</h3>
<p>
  <input type="hidden" name="mode" value="ticket" />
  <input type="hidden" name="id"   value="<?cs var:ticket.id ?>" />
</p>
<table class="listing">
  <tr>
    <td align="right">opened:</td><td><?cs var:ticket.opened ?></td>
    <td align="right">reporter:</td><td><?cs var:ticket.reporter ?></td>
  </tr>
  <tr>
    <td align="right">component:</td>
    <td><?cs call:hdf_select(ticket.components, 
                             "component",
                             ticket.component) ?>
    </td>
    <td align="right">priority:</td>
    <td><?cs call:hdf_select(enums.priority, 
                             "priority",
                             ticket.priority) ?>
    </td>
  </tr>
  <tr>
    <td align="right">version:</td>
    <td><?cs call:hdf_select(ticket.versions, 
                             "version",
                             ticket.version) ?>
    </td>
    <td align="right">milestone:</td>
    <td><?cs call:hdf_select(ticket.milestones, 
                             "milestone",
                             ticket.milestone) ?>
    </td>
  </tr>
  <tr>
    <td align="right">severity:</td>
    <td><?cs call:hdf_select(enums.severity, 
                             "severity",
                             ticket.severity) ?>
    </td>
    <td align="right">assigned to:</td><td><?cs var:ticket.owner ?></td>
  </tr>
  <tr>
    <td align="right">status:</td>
    <td><?cs var:ticket.status ?></td>
<td align="right">resolution:</td><td><?cs var:ticket.resolution ?></td>
</tr>
<tr>
<td align="right">cc:</td>
<td><input type="text" name="cc" value="<?cs var:ticket.cc ?>" /></td>
</tr>
<tr>
<td align="right"><a href="<?cs var:ticket.url ?>">url</a>:</td>
<td colspan="3">
  <input type="text" name="url" value="<?cs var:ticket.url ?>" size="50" /></td>
</tr>
<tr>
<td align="right">summary:</td>
<td colspan="3">
  <input type="text" name="summary" value="<?cs var:ticket.summary ?>"
  size="50" /></td>
</tr>
<tr>
<td align="right">additional comments:</td>
	<td colspan="3">
	<textarea name="comment" rows="8" cols="70"></textarea>
	</td>
</tr>
<tr>
<td></td>
<td colspan="3">
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

</td>
</tr>
<tr>
<td></td>
<td colspan="3"><br /><input type="submit" value="commit" /> </td>
</tr>
</table>
</form>

 </div>
</div>
</div>
<?cs include:"footer.cs"?>

