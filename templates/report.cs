<?cs include "../templates/header.cs" ?>

<h3>Reports</h3>

<?cs if report.mode == "list" ?>

  <h3><?cs var:report.title ?></h3>

  <?cs if report.create_href ?>
    <a href="<?cs var:report.create_href ?>">create</a> |
  <?cs /if ?>
  <?cs if report.edit_href ?>
    <a href="<?cs var:report.edit_href ?>">edit</a> |
  <?cs /if ?>
  <?cs if report.copy_href ?>
    <a href="<?cs var:report.copy_href ?>">copy</a> |
  <?cs /if ?>
  <?cs if report.delete_href ?>
    <a href="<?cs var:report.delete_href ?>">delete</a> |
  <?cs /if ?>

  <table class="listing" cellspacing="0" cellpadding="0">
    <tr>
      <?cs each header = report.headers ?>
        <th class="listing"><?cs var:header.title ?></th>
      <?cs /each ?>
    </tr>

    <?cs set idx = #0 ?>

    <?cs each row = report.items ?>

      <?cs if idx % #2 ?>
        <tr class="item-row-even">
      <?cs else ?>
        <tr class="item-row-odd">
      <?cs /if ?>
      <?cs set idx = idx + #1 ?>

      <?cs each cell = row ?>

        <?cs if cell.type == "ticket" ?>
          <td class="ticket-column"><a href="<?cs var:cell.ticket_href ?>" ?>#<?cs var: cell.value ?></a></td>
        <?cs elif cell.type == "report" ?>
          <td class="report-column"><a href="<?cs var:cell.report_href ?>">{<?cs var: cell.value ?>}</a></td>
        <?cs elif cell.type == "time" ?>
          <td class="date-column"><?cs var: cell.value ?></td>
        <?cs else ?>
          <td><?cs var: cell.value ?></td>
        <?cs /if ?>

      <?cs /each ?>
      </tr>
    <?cs /each ?>
  </table>

<?cs elif report.mode == "editor" ?>

  <form action="<?cs var:cgi_name ?>" method="post">
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


<?cs include "../templates/footer.cs" ?>
