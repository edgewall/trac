<?cs include "header.cs" ?>
<div id="page-content">
<div id="subheader-links">
  <?cs if report.edit_href || report.copy_href || report.delete_href ?>
  <?cs if report.edit_href ?>
    <span class="subheader-sublinks"><b>This report:</b>&nbsp;
      [ <a href="<?cs var:report.edit_href ?>">edit</a>&nbsp;
  <?cs /if ?>
  <?cs if report.copy_href ?>
   | <a href="<?cs var:report.copy_href ?>">copy</a>&nbsp;
  <?cs /if ?>
  <?cs if report.delete_href ?>
   | <a href="<?cs var:report.delete_href ?>">delete</a>
  <?cs /if ?>
  ]</span> |
  <?cs /if ?>
  <?cs if report.create_href ?>
   <a href="<?cs var:report.create_href ?>">New Report</a>&nbsp;|
  <?cs /if ?>
  <a href="<?cs var:$trac.href.report ?>">Report Index</a>&nbsp;
</div>


<?cs if report.mode == "list" ?>

  <div class="report-sidebar">
  </div>

  <h1 id="report-hdr"><?cs var:report.title ?></h1>

  <table id="browser-list" cellspacing="0" cellpadding="0">
    <tr>
      <?cs each header = report.headers ?>
        <th class="header-left"><?cs var:header.title ?></th>
      <?cs /each ?>
    </tr>

    <?cs set idx = #0 ?>

    <?cs each row = report.items ?>

      <?cs if idx % #2 ?>
        <tr class="row-even">
      <?cs else ?>
        <tr class="row-odd">
      <?cs /if ?>
      <?cs set idx = idx + #1 ?>

      <?cs each cell = row ?>

        <?cs if cell.type == "ticket" ?>
          <td class="ticket-column"><a href="<?cs var:cell.ticket_href ?>" ?>#<?cs var: cell.value ?></a></td>
        <?cs elif cell.type == "report" ?>
          <td class="report-column"><a href="<?cs var:cell.report_href ?>">{<?cs var: cell.value ?>}</a></td>
        <?cs elif cell.type == "time" ?>
          <td class="date-column"><?cs var: cell.value ?></td>
        <?cs elif cell.type == "summary" ?>
          <td class="summary-column"><?cs var: cell.value ?></td>
        <?cs elif cell.type == "owner" ?>
          <td class="owner-column"><?cs var: cell.value ?></td>
        <?cs elif cell.type == "severity" ?>
          <td class="severity-column"><?cs var: cell.value ?></td>
        <?cs elif cell.type == "priority" ?>
          <td class="priority-column"><?cs var: cell.value ?></td>
        <?cs elif cell.type == "status" ?>
          <td class="status-column"><?cs var: cell.value ?></td>
        <?cs else ?>
          <td><?cs var: cell.value ?></td>
        <?cs /if ?>

      <?cs /each ?>
      </tr>
    <?cs /each ?>
  </table>

<?cs elif report.mode == "editor" ?>

  <form action="<?cs var:cgi_location ?>" method="POST">
    <input type="hidden" name="mode" value="report">
    <input type="hidden" name="id" value="<?cs var:report.id ?>">
    <input type="hidden" name="action" value="<?cs var:report.action ?>">
    title:<br><input type="text" name="title" value="<?cs var:report.title ?>" size="50">
    <br>sql query:
    <br>
    <textarea name="sql" cols="70" rows="10"><?cs var:report.sql ?></textarea>
    <br>
    <input type="submit" value="commit">&nbsp;
    <input type="reset" value="reset">
  </form>


<?cs /if?>


 </div>
</div>
</div>
<?cs include:"footer.cs"?>
