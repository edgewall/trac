<?cs include "header.cs"?>

<h3>Log history for: <?cs var:log.path ?></h3>

<table class="listing" cellspacing="0" cellpadding="0">
<tr class="listing-header">
  <th class="listing">date</th>
  <th class="listing">revision</th>
  <th class="listing">change set</th>
  <th class="listing">log message</th>
</tr>

<?cs each:item = log.items ?>
  <?cs if idx % #2 ?>
    <tr class="item-row-even">
  <?cs else ?>
    <tr class="item-row-odd">
  <?cs /if ?>
            
  <td class="date-column"><?cs var:item.date ?></td>
  <td class="rev-column">
    <a href="<?cs var:item.file_href ?>"><?cs var:item.rev ?></a>
  </td>
  <td class="rev-column">
    <a href="<?cs var:item.changeset_href ?>"><?cs var:item.rev ?></a>
  </td>
  <td class="summary-column"><?cs var:item.log ?></td>
  </tr>

<?cs /each ?>

</table>

<?cs include "footer.cs"?>
