<?cs include "../templates/header.cs" ?>
<?cs include "../templates/macros.cs" ?>

<h3>ticket: #<?cs var:ticket.id ?></h3>

<!-- Short summary -->
<table class="listing">
<tr>
  <th class="header-left">Component</th>
  <th class="header-left">Version</th>
  <th class="header-left">Status</th>
  <th class="header-left" width="50%">Summary</th>
</tr>
<tr>
  <td><?cs var:ticket.component ?></td>
  <td><?cs var:ticket.version ?></td>
  <td><?cs var:ticket.status ?></td>
  <td><?cs var:ticket.summary ?></td>
</tr>
</table>

<!-- Long description -->
<p>
  <br>Description:
</p>
<table class="listing">
<tr>
  <td colspan="4">

  <!-- First the original description -->
  <div class="ticket-modified">description by 
    <?cs var:ticket.reporter ?> <?cs var:ticket.opened ?>:
  </div>
  <?cs var:ticket.description ?>

  <!-- Then eventual additional comments -->
  <?cs set:comment = "" ?>
  <?cs set:curr_date = "" ?>
  <?cs set:curr_author = "" ?>

  <?cs each:item = ticket.changes ?>
    <?cs if $item.date != $curr_date || $item.author != $curr_author ?>
      <?cs if $comment != "" ?>
        <p>comment: <?cs var:$comment ?></p>
        <?cs set:comment = "" ?>
      <?cs /if ?>
      <?cs set:curr_date = $item.date ?>
      <?cs set:curr_author = $item.author ?>
      <div class="ticket-modified">modified by 
        <?cs var:curr_author ?> <?cs var:curr_date ?>:
      </div>
    <?cs /if ?>
    <?cs if $item.field == "comment" ?>
      <p><?cs set:$comment = $item.new ?></p>
    <?cs elif $item.new == "" ?>
      <p>cleared <b><?cs var:item.field?></b></p>
    <?cs elif $item.old == "" ?>
      <p><b><?cs var:item.field ?></b> set to <b><?cs var:item.new ?></b></p>
    <?cs else ?>
      <p><b><?cs var:item.field ?></b> changed from
         <b><?cs var:item.old ?></b> to
         <b><?cs var:item.new ?></b></p>
    <?cs /if ?>
  <?cs /each ?>
  <?cs if $comment != "" ?>
    <p>comment: <?cs var:$comment ?></p>
  <?cs /if ?>
  </td>
</tr>
</table>

<form action="<?cs var:cgi_location ?>" method="POST">
<input type="hidden" name="mode" value="ticket">
<input type="hidden" name="id"   value="<?cs var:ticket.id ?>">

<p>
  <br>Additional information:
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
<td><input type="text" name="cc" value="<?cs var:ticket.cc ?>"></td>
</tr>
<tr>
<td align="right"><a href="<?cs var:ticket.url ?>">url</a>:</td>
<td colspan="3"><input type="text" name="url" value="<?cs var:ticket.url ?>" size="50"></td>
</tr>
<tr>
</tr>
<tr>
<td align="right">summary:</td>
<td colspan="3"><input type="text" name="summary" value="<?cs var:ticket.summary ?>" size="50"></td>
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


  <input type="radio" name="action" value="leave" checked="checked">
  &nbsp;leave as <?cs var:ticket.status ?><br>
 
  <?cs if $ticket.status == "new" ?>
    <input type="radio" name="action" value="accept">
    &nbsp;accept ticket<br>
  <?cs /if ?>
  <?cs if $ticket.status == "closed" ?>
    <input type="radio" name="action" value="reopen">
    &nbsp;reopen ticket<br>
  <?cs /if ?>
  <?cs if $ticket.status == "new" || $ticket.status == "assigned" || $ticket.status == "reopened" ?>
    <input type="radio" name="action" value="resolve">
    &nbsp;resolve as: 
    <select name="resolve_resolution">
      <option selected>fixed</option>
      <option>invalid</option>
      <option>wontfix</option>
      <option>duplicate</option>
      <option>worksforme</option>
    </select><br>
    <input type="radio" name="action" value="reassign">
    &nbsp;reassign ticket to:
    &nbsp<input type="text" name="reassign_owner" 
          value="<?cs var:ticket.owner ?>">
  <?cs /if ?>

</td>
</tr>
<tr>
<td></td>
<td colspan="3"><br><input type="submit" value="commit">
</tr>
</table>
</form>

<?cs include "../templates/footer.cs" ?>
