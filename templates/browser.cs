<?cs include: "header.cs"?>
<?cs include "macros.cs"?>
<div id="page-content">
 <ul class="subheader-links">
   <li class="last">&nbsp;</li>
 </ul>
 <div id="main">
  <div id="main-content">
   <h1 id="browser-rev" class="hide">Browsing Revision <?cs var:browser.revision?></h1>
   <div id="browser-body">
    <?cs call:browser_path_links(browser.path, browser) ?>
    <div id="browser-nav">
    <form id="browser-chgrev" action="<?cs var:browser_current_href ?>" 
          method="get">
      <div>
        View rev:
        <input type="text" name="rev" value="<?cs var:browser.revision?>"
          size="4" />
        <input type="submit" value="View" />
      </div></form>
    <div class="tiny" style="clear: both">&nbsp;</div>
    </div>
    <table id="browser-list" cellspacing="0" cellpadding="0">
      <tr class="browser-listhdr">
        <th>&nbsp;</th>
<?cs if browser.sort_order == "name" ?>
        <th><a title="Sort by Name (Descending)" href="<?cs var:browser.current_href?>?order=Name">Name</a></th>
<?cs else ?>
        <th><a title="Sort by Name" href="<?cs var:browser.current_href?>?order=name">Name</a></th>
<?cs /if ?>
<?cs if browser.sort_order == "size" ?>
        <th><a title="Sort by size (Descending)" href="<?cs var:browser.current_href?>?order=Size">Size</a></th>
<?cs else ?>
        <th><a title="Sort by size" href="<?cs var:browser.current_href?>?order=size">Size</a></th>
<?cs /if ?>
        <th>Rev</th>
<?cs if browser.sort_order == "date" ?>
        <th><a title="Sort by Age" href="<?cs var:browser.current_href?>?order=Date">Age</a></th>
<?cs else ?>
        <th><a title="Sort by Age (Descending)" href="<?cs var:browser.current_href?>?order=date">Age</a></th>
<?cs /if ?>
      </tr>
      <?cs if $browser.path != "/" ?>
        <tr class="br-row-even">
          <td class="br-icon-col">
            <a title="Parent Directory" class="block-link" href="<?cs var:browser.parent_href ?>">
              <img src="<?cs var:htdocs_location ?>parent.png" 
                    width="16" height="16" alt="[parent]" />
            </a>
          </td>
          <td class="br-name-col">
            <a title="Parent Directory" class="block-link"  href="<?cs var:browser.parent_href ?>">..</a>
          </td>
          <td class="br-size-col">&nbsp;</td>
          <td class="br-rev-col">&nbsp;</td>
          <td class="br-age-col">&nbsp;</td>
        </tr>
      <?cs /if ?>
      <?cs set:idx = #0 ?>
      <?cs each:item = browser.items ?>
        <?cs if idx % #2 ?>
          <tr class="even">
        <?cs else ?>
          <tr class="odd">
        <?cs /if ?>
        <?cs if item.is_dir == #1 ?>
          <td class="br-icon-col">
            <a title="Browse Directory" class="block-link"  href="<?cs var:item.browser_href ?>">
              <img src="<?cs var:htdocs_location ?>folder.png"
                    width="16" height="16" alt="[dir]" />
            </a>
          </td>
          <td class="br-name-col">
            <a title="Browse Directory" class="block-link"  href="<?cs var:item.browser_href ?>"><?cs var:item.name ?></a>
          </td>
        <?cs else ?>
          <td class="br-icon-col">
            <a title="View File" class="block-link"  href="<?cs var:item.browser_href ?>">
              <img src="<?cs var:htdocs_location ?>file.png"
                    width="16" height="16" alt="[file]" />
            </a>
          </td>
          <td class="br-name-col">
            <a title="View File" class="block-link"  href="<?cs var:item.browser_href ?>"><?cs var:item.name ?></a>
          </td>
         <?cs /if ?>
         <td class="br-size-col">
           <?cs if item.size != #0 ?><?cs var:item.size ?><?cs /if ?>
         </td>
         <td class="br-rev-col">
           <a title="View Revision Log" class="block-link-nobold" 
              href="<?cs var:item.log_href ?>"><?cs var:item.created_rev ?></a>
         </td>
         <td class="br-age-col">
          <a class="age" title="<?cs var:item.date ?>"><?cs var:item.age ?></a>
         </td>
       </tr>
       <?cs set:idx = idx + #1 ?>
     <?cs /each ?>
   </table>
<div id="help">
<strong>Note:</strong> See <a href="<?cs var:$trac.href.wiki
?>/TracBrowser">TracBrowser</a> for help on using the browser.
</div>
  </div>


 </div>
</div>
</div>
<?cs include:"footer.cs"?>
