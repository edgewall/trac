<?cs include "../templates/header.cs"?>

<h3>Timeline</h3>

<table>

<?cs def:day_separator(date) ?>
  <?cs if: $date != $current_date ?>
    <?cs set: $current_date = $date ?>
    <tr>
      <td colspan="2" class="timeline-day"><?cs var:date?>:</td>
    </tr>
  <?cs /if ?>
<?cs /def ?>

<?cs each:item = timeline.items ?>

  <?cs call:day_separator(item.date) ?>
<!-- Changeset -->
  <?cs if:item.type == #1 ?>
    <tr>
      <td><?cs var:item.time?></td>
      <td>change set [<a href="<?cs var:item.changeset_href ?>"><?cs var:item.data?></a>] by <?cs var:item.author ?>: <?cs var:item.message?></td>
    </tr>
<!-- New ticket -->
  <?cs elif:item.type == #2 ?>
    <tr>
      <td><?cs var:item.time?></td>
      <td>ticket <a href="<?cs var:item.ticket_href ?>">#<?cs var:item.data?></a> created by <?cs var:item.author ?>: <?cs var:item.message?>.</td>
    </tr>
<!-- Closed ticket -->
  <?cs elif:item.type == #3 ?>
    <tr>
      <td><?cs var:item.time?></td>
      <td>ticket <a href="<?cs var:item.ticket_href ?>">#<?cs var:item.data?></a> closed by <?cs var:item.author ?>.</td>
    </tr>
<!-- Reopened ticket -->
  <?cs elif:item.type == #4 ?>
    <tr>
      <td><?cs var:item.time?></td>
      <td>ticket <a href="<?cs var:item.ticket_href ?>">#<?cs var:item.data?></a> reopened by <?cs var:item.author ?>.</td>
    </tr>
  <?cs /if ?>
<?cs /each ?>

</table>

<?cs include "../templates/footer.cs"?>

