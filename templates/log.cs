<?cs include "header.cs"?>
<div id="page-content">
 <div id="subheader-links">
 </div>
 <div id="main">
  <div id="main-content">

<h1 id="log-hdr">Log history for <?cs var:log.path ?></a></h1>

<div id="browser-pathlinks">
  <?cs each:part=log.path ?>
    <a href="<?cs var:part.url ?>"><?cs var:part?></a> /
  <?cs /each ?>
  <?cs var:log.filename ?>
</div>

<table id="browser-list" cellspacing="0" cellpadding="0">
<tr class="browser-listhdr">
  <th>Date</th>
  <th>Rev</th>
  <th>Chgset</th>
  <th>Log Message</th>
</tr>

<?cs each:item = log.items ?>
  <?cs if idx % #2 ?>
    <tr class="br-row-even">
  <?cs else ?>
    <tr class="br-row-odd">
  <?cs /if ?>
            
  <td class="br-date-col"><?cs var:item.date ?></td>
  <td class="br-rev-col">
    <a href="<?cs var:item.file_href ?>"><?cs var:item.rev ?></a>
  </td>
  <td class="br-chg-col">
    <a href="<?cs var:item.changeset_href ?>"><?cs var:item.rev ?></a>
  </td>
  <td class="br-summary-col"><?cs var:item.log ?></td>
  </tr>
  <?cs set:idx = idx + #1 ?>
<?cs /each ?>

</table>

 </div>
</div>
</div>
<?cs include:"footer.cs"?>

