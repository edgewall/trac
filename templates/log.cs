<?cs include "header.cs"?>
<?cs include "macros.cs"?>
<div id="page-content">
<ul class="subheader-links">
  <li class="last"><a href="<?cs
    var:log.items.0.file_href ?>">View Latest Revision</a></li>
</ul>

 <div id="main">
  <div id="main-content">
  <h1 id="log-hdr" class="hide">Revision log for <?cs var:log.path ?></h1>
  <?cs call:browser_path_links(log.path, log) ?>
  <div id="browser-nav">
  <ul class="menulist"><li class="last"><a 
     href="<?cs var:log.items.0.file_href ?>">View Latest Revision</a></li></ul>
    <form id="browser-chgrev" action="<?cs var:log.items.0.file_href ?>" method="get">
      <label for="rev">View rev:</label>
      <input type="text" id="rev" name="rev" value="<?cs
        var:log.items.0.rev ?>" size="4" />
      <input type="submit" value="View"/>
    </form>
    <div class="tiny" style="clear: both">&nbsp;</div>
  </div>
  <table id="browser-list" cellspacing="0" cellpadding="0">
    <tr class="browser-listhdr">
      <th>Date</th>
      <th>Rev</th>
      <th>Chgset</th>
      <th>Author</th>
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
	<a class="block-link" href="<?cs var:item.file_href ?>"><?cs var:item.rev ?></a>
      </td>
      <td class="br-chg-col">
	<a class="block-link" href="<?cs var:item.changeset_href ?>"><?cs var:item.rev ?></a>
      </td>
      <td class="br-author-col">
	<?cs var:item.author ?>
      </td>
      <td class="br-summary-col"><?cs var:item.log ?></td>
    </tr>
    <?cs set:idx = idx + #1 ?>
    <?cs /each ?>
  </table>
 <div id="main-footer">
   Download history in other formats: <br />
   <a class="noline" href="?format=rss"><img src="<?cs var:htdocs_location
						  ?>xml.png" alt="RSS Feed" style="vertical-align: bottom"/></a>&nbsp;
   <a href="?format=rss">(RSS 2.0)</a>
   <br />
 </div>

 </div>
</div>
</div>
<?cs include:"footer.cs"?>

