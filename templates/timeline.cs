<?cs include "header.cs"?>

<h3>Timeline</h3>


<form action="<?cs var:cgi_location ?>">
<div>
View changes from 
<input type="hidden" name="mode" value="timeline">
<input size="10" name="from" value="<?cs var:timeline.from ?>"> 
and 
<input size="3" name="daysback" value="<?cs var:timeline.daysback ?>">
days back:<br>
<input type="checkbox" name="ticket" <?cs var:timeline.ticket ?>>
view ticket changes<br>
<input type="checkbox" name="changeset" <?cs var:timeline.changeset ?>>
view repository checkins<br>
<input type="checkbox" name="wiki" <?cs var:timeline.wiki ?>>
view wiki changes<br>
<br>
<input type="submit" value="Update"> <input type="reset">
</div>
</form>


<table>

<?cs def:day_separator(date) ?>
  <?cs if: $date != $current_date ?>
    <?cs set: $current_date = $date ?>
    <tr>
      <td colspan="2" class="timeline-day"><?cs var:date ?>:</td>
    </tr>
  <?cs /if ?>
<?cs /def ?>

<?cs each:item = timeline.items ?>

  <?cs call:day_separator(item.date) ?>
<!-- Changeset -->
  <?cs if:item.type == #1 ?>
    <tr>
      <td><?cs var:item.time?></td>
      <td><img align="left" src="<?cs var:htdocs_location?>/changeset.png">: change set [<a href="<?cs var:item.changeset_href ?>"><?cs var:item.data?></a>] by <?cs var:item.author ?>: <?cs var:item.message?></td>
    </tr>
<!-- New ticket -->
  <?cs elif:item.type == #2 ?>
    <tr>
      <td><?cs var:item.time?></td>
      <td><img align="left" src="<?cs var:htdocs_location?>/newticket.png">: ticket <a href="<?cs var:item.ticket_href ?>">#<?cs var:item.data?></a> created by <?cs var:item.author ?>: <?cs var:item.message?>.</td>
    </tr>
<!-- Closed ticket -->
  <?cs elif:item.type == #3 ?>
    <tr>
      <td><?cs var:item.time?></td>
      <td><img align="left" src="<?cs var:htdocs_location?>/closedticket.png">: ticket <a href="<?cs var:item.ticket_href ?>">#<?cs var:item.data?></a> closed by <?cs var:item.author ?>.</td>
    </tr>
<!-- Reopened ticket -->
  <?cs elif:item.type == #4 ?>
    <tr>
      <td><?cs var:item.time?></td>
      <td><img align="left" src="<?cs var:htdocs_location?>/newticket.png">: ticket <a href="<?cs var:item.ticket_href ?>">#<?cs var:item.data?></a> reopened by <?cs var:item.author ?>.</td>
    </tr>
<!-- Wiki change -->
  <?cs elif:item.type == #5 ?>
    <tr>
      <td><?cs var:item.time?></td>
      <td><img align="left" src="<?cs var:htdocs_location?>/wiki.png">: <a href="<?cs var:item.wiki_href ?>"><?cs var:item.data?></a> edited by <?cs var:item.author ?>.</td>
    </tr>
  <?cs /if ?>
<?cs /each ?>

</table>

<?cs include "footer.cs"?>

