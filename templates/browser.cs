<?cs include: "header.cs"?>
<?cs include "macros.cs"?>

<div class="nav">
</div>

<div id="main" class="browser">
 <h1 id="browser-rev" class="hide">Browsing Revision <?cs var:browser.revision?></h1>
 <?cs call:browser_path_links(browser.path, browser) ?>

 <div id="browser-nav">
  <form id="browser-chgrev" action="<?cs var:browser_current_href ?>" method="get">
   <div>
    <label for="rev">View rev:</label>
    <input type="text" id="rev" name="rev" value="<?cs
      var:browser.revision?>" size="4" />
    <input type="submit" value="View" />
   </div>
  </form>
 </div>

 <table class="listing" id="dirlist">
  <thead>
   <tr>
    <th class="name"><?cs
     if browser.sort_order == "name" ?>
      <a title="Sort by Name (Descending)" href="<?cs
        var:browser.current_href?>?order=Name">Name</a><?cs
     else ?>
      <a title="Sort by Name" href="<?cs
        var:browser.current_href?>?order=name">Name</a><?cs
     /if ?></th>
    <th class="rev">Rev</th>
    <th class="age"><?cs
     if browser.sort_order == "date" ?>
      <a title="Sort by Age" href="<?cs
        var:browser.current_href?>?order=Date">Age</a><?cs
     else ?>
      <a title="Sort by Age (Descending)" href="<?cs
        var:browser.current_href?>?order=date">Age</a><?cs
     /if ?></th>
    <th class="change">Last Change</th>
   </tr>
  </thead>
  <tbody>
   <?cs if $browser.path != "/" ?>
    <tr class="even">
     <td class="name" colspan="4">
      <a class="parent" title="Parent Directory" href="<?cs
        var:browser.parent_href ?>">../</a>
     </td>
    </tr>
   <?cs /if ?>
   <?cs each:item = browser.items ?>
    <tr class="<?cs if:name(item) % #2 ?>even<?cs else ?>odd<?cs /if ?>">
     <td class="name"><?cs
      if:item.is_dir ?>
       <a class="dir" title="Browse Directory" href="<?cs
         var:item.browser_href ?>"><?cs var:item.name ?></a><?cs
      else ?>
       <a class="file" title="View File" href="<?cs
         var:item.browser_href ?>"><?cs var:item.name ?></a><?cs
      /if ?>
     </td>
     <td class="rev"><a title="View Revision Log" href="<?cs
       var:item.log_href ?>"><?cs var:item.created_rev ?></a></td>
     <td class="age"><span title="<?cs var:item.date ?>"><?cs
       var:item.age ?></span></td>
     <td class="change">
      <span class="author"><?cs var:item.author ?>:</span>
      <span class="change"><?cs var:item.change ?></span>
     </td>
    </tr>
   <?cs /each ?>
  </tbody>
 </table>

 <div id="help">
  <strong>Note:</strong> See <a href="<?cs var:$trac.href.wiki
  ?>/TracBrowser">TracBrowser</a> for help on using the browser.
 </div>

</div>
<?cs include:"footer.cs"?>
