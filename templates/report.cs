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
    <hr class="hide"/>
    <h2 class="report-hdr"><?cs var:header ?></h2>
  <?cs /if ?>
  <table class="report-list" cellspacing="0" cellpadding="0">
    <tr>
      <?cs set numcols = #0 ?>
      <?cs each header = report.headers ?>
        <?cs if $header.fullrow ?>
          </tr><tr><th class="header-left" colspan="100"><?cs var:header ?></th>
        <?cs else ?>
          <th class="header-left"><?cs var:header ?></th>
          <?cs if $header.breakrow ?>
             </tr><tr>
          <?cs /if ?>
        <?cs /if ?>
        <?cs set numcols = numcols + #1 ?>
      <?cs /each ?>
    </tr>
<?cs /def ?>

<?cs def:report_cell(class,contents) ?>
  <?cs if $cell.fullrow ?>
    </tr><tr class="<?cs var: row_class ?>" style="border: none; padding: 0">
<td colspan="100" style="padding: 0;border: none"><div class="report-fullrow"><?cs var:$contents ?></div><hr class="hide"/></td>
  <?cs else ?>
  <td <?cs if $cell.breakrow || $col == $numcols ?>colspan="100" <?cs /if
?>class="<?cs var:$class ?>"><?cs if $contents ?><?cs var:$contents ?><?cs /if ?></td>

<?cs if $cell.breakafter ?>
    </tr><tr class="<?cs var: row_class ?>" style="border: none; padding: 0">
<?cs /if ?>
  <?cs /if ?>
  <?cs set col = $col + #1 ?>
<?cs /def ?>

<?cs set idx = #0 ?>
<?cs set group = '' ?>

<?cs if report.mode == "list" ?>
  <h1 id="report-hdr"><?cs var:report.title ?></h1>

    <?cs each row = report.items ?>

      <?cs if group != row.__group__ || idx == #0 ?>
        <?cs set group = row.__group__ ?>
        <?cs call:report_hdr(group) ?>
      <?cs /if ?>
    
      <?cs if row.__color__ ?>
        <?cs set rstem='color'+$row.__color__ ?>
      <?cs else ?>
       <?cs set rstem='row' ?>
      <?cs /if ?>
      <?cs if idx % #2 ?>
        <?cs set row_class=$rstem+'-even' ?>
      <?cs else ?>
        <?cs set row_class=$rstem+'-odd' ?>
      <?cs /if ?>

      <?cs set row_style='' ?>
      <?cs if row.__bgcolor__ ?>
        <?cs set row_style='background: ' + row.__bgcolor__ + ';' ?>
      <?cs /if ?>
      <?cs if row.__fgcolor__ ?>
        <?cs set row_style=$row_style + 'color: ' + row.__fgcolor__ + ';' ?>
      <?cs /if ?>
      <?cs if row.__style__ ?>
        <?cs set row_style=$row_style + row.__style__ + ';' ?>
      <?cs /if ?>
    
      <tr class="<?cs var: row_class ?>" style="<?cs var: row_style ?>">
      <?cs set idx = idx + #1 ?>
      <?cs set col = #0 ?>
      <?cs each cell = row ?>
        <?cs if cell.hidden || cell.hidehtml ?>    
        <?cs elif name(cell) == "ticket" ?>
          <?cs call:report_cell('ticket-col', 
            	                '<a class="report-tktref" href="'+
                                $cell.ticket_href+'">#'+$cell+'</a>') ?>
        <?cs elif name(cell) == "report" ?>
          <?cs call:report_cell('report-col', 
               '<a href="'+$cell.report_href+'">{'+$cell+'}</a>') ?>
        <?cs elif name(cell) == "time" ?>
          <?cs call:report_cell('date-column', $cell.date) ?>
        <?cs elif name(cell) == "date" || name(cell) == "created" || name(cell) == "modified" ?>
          <?cs call:report_cell('date-column', $cell.date) ?>
        <?cs elif name(cell) == "datetime"  ?>
          <?cs call:report_cell('date-column', $cell.datetime) ?>
        <?cs elif name(cell) == "description" ?>
          <?cs call:report_cell('', $cell.parsed) ?>
        <?cs else ?>
          <?cs call:report_cell(name(cell)+'-col', $cell) ?>
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
      <input type="submit" value="Save" />&nbsp;
      <input type="submit" name="view" value="Cancel" />
    </div>
  </form>
<?cs /if?>

<div id="help">
 <strong>Note:</strong> See <a href="<?cs var:$trac.href.wiki ?>TracReports">TracReports</a> 
 for help on reports.
</div>

<?cs if report.id > #0 ?>
 <div id="main-footer">
  Download report in other data formats: <br />
  <a class="noline" href="?format=rss"><img src="<?cs var:htdocs_location
?>xml.png" alt="RSS Feed" style="vertical-align: bottom"/></a>&nbsp;
  <a href="?format=rss">(RSS 2.0)</a>&nbsp;|
  <a href="?format=csv">Comma-delimited</a>&nbsp;|
  <a href="?format=tab">Tab-delimited</a>
  <br />
 </div>
<?cs /if ?>



  </div>
 </div>


</div>
<?cs include:"footer.cs"?>
