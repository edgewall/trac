<?cs include "header.cs" ?>
<div id="page-content">
<div id="subheader-links">
  <?cs if report.edit_href || report.copy_href || report.delete_href ?>
  <?cs if report.edit_href?>
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
<hr class="hide"/>
<div id="main">
    <div id="main-content">


<?cs def:report_hdr(header) ?>
  <?cs if $header ?>
    <?cs if idx > 0 ?>
      </table>
    <?cs /if ?>
    <h2 class="report-hdr"><?cs var:header ?></h2>
  <?cs /if ?>
  <table class="report-list" cellspacing="0" cellpadding="0">
    <tr>
      <?cs each header = report.headers ?>
        <th class="header-left"><?cs var:header.title ?></th>
      <?cs /each ?>
    </tr>
<?cs /def ?>

<?cs set idx = #0 ?>
<?cs set group = '' ?>

<?cs if report.mode == "list" ?>
  <h1 id="report-hdr"><?cs var:report.title ?></h1>

    <?cs each row = report.items ?>

      <?cs if group != row._group.value || idx == #0 ?>
        <?cs set group = row._group.value ?>
        <?cs call:report_hdr(group) ?>
      <?cs /if ?>
    
      <?cs if row._color.value ?>
        <?cs set rstem='color'+$row._color.value ?>
      <?cs else ?>
       <?cs set rstem='row' ?>
      <?cs /if ?>
      <?cs if idx % #2 ?>
        <?cs set row_class=$rstem+'-even' ?>
      <?cs else ?>
        <?cs set row_class=$rstem+'-odd' ?>
      <?cs /if ?>

      <?cs set row_style='' ?>
      <?cs if row._bgcolor.value ?>
        <?cs set row_style='background: ' + row._bgcolor.value + ';' ?>
      <?cs /if ?>
      <?cs if row._fgcolor.value ?>
        <?cs set row_style=$row_style + 'color: ' + row._fgcolor.value + ';' ?>
      <?cs /if ?>
      <?cs if row._style.value ?>
        <?cs set row_style=$row_style + row._style.value + ';' ?>
      <?cs /if ?>
    
      <tr class="<?cs var: row_class ?>" style="<?cs var: row_style ?>">
	<?cs set idx = idx + #1 ?>
      <?cs each cell = row ?>
        <?cs if cell.type == "special" ?>    
        <?cs elif cell.type == "ticket" ?>
          <td class="ticket-column"><a class="report-tktref" href="<?cs var:cell.ticket_href ?>">#<?cs var: cell.value ?></a></td>
        <?cs elif cell.type == "report" ?>
          <td class="report-col"><a href="<?cs var:cell.report_href ?>">{<?cs var: cell.value ?>}</a></td>
        <?cs elif cell.type == "time" ?>
          <td class="date-column"><?cs var: cell.value ?></td>
        <?cs elif cell.type == "summary" ?>
          <td class="summary-col"><?cs var: cell.value ?></td>
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

  <h1 id="report-hdr">Create New Report</h1>
  
  <form action="<?cs var:cgi_location ?>" method="post">
    <div>
      <input type="hidden" name="mode" value="report" />
      <input type="hidden" name="id" value="<?cs var:report.id ?>" />
      <input type="hidden" name="action" value="<?cs var:report.action ?>" />
      Report Title:<br />
      <input type="text" name="title" value="<?cs var:report.title ?>"
              size="50" />
      <br />SQL Query: <br />
      <textarea name="sql" cols="70" rows="10"><?cs var:report.sql ?></textarea>
      <br />
      <input type="submit" value="commit" />&nbsp;
      <input type="reset" value="reset" />
    </div>
  </form>


<?cs /if?>
<br />
  </div>
 </div>
</div>
<?cs include:"footer.cs"?>
