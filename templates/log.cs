<?cs set:html.stylesheet = 'css/browser.css' ?>
<?cs include "header.cs"?>
<?cs include "macros.cs"?>

<div id="ctxtnav" class="nav">
 <ul>
  <li class="last"><a href="<?cs
    var:log.browser_href ?>">View Latest Revision</a></li><?cs
  if:len(links.prev) ?>
   <li class="first<?cs if:!len(links.next) ?> last<?cs /if ?>">
    &larr; <a href="<?cs var:links.prev.0.href ?>" title="<?cs
      var:links.prev.0.title ?>">Newer Revisions</a>
   </li><?cs
  /if ?><?cs
  if:len(links.next) ?>
   <li class="<?cs if:!len(links.prev) ?>first <?cs /if ?>last">
    <a href="<?cs var:links.next.0.href ?>" title="<?cs
      var:links.next.0.title ?>">Older Revisions</a> &rarr;
   </li><?cs
  /if ?>
 </ul>
</div>


<div id="content" class="log">
 <?cs call:browser_path_links(log.path, log) ?>
 <h3>Revision Log showing <?cs
  if:log.mode == "path" ?>
   Path History, up to Revision <?cs var:log.rev ?><?cs
  else ?>
   Node History, starting at Revision <?cs var:log.rev ?><?cs
  /if ?><?cs 
  if:len(links.prev) + len(links.next) > #0 ?>
   (Page <?cs var:log.page ?>)<?cs
  /if ?>
 </h3>

 <div class="diff">
  <div id="legend">
   <h3>Legend:</h3>
   <dl>
    <dt class="add"></dt><dd>Added</dd><?cs
    if:log.mode == "path" ?>
     <dt class="rem"></dt><dd>Removed</dd><?cs
    /if ?>
    <dt class="mod"></dt><dd>Modified</dd>
    <dt class="cp"></dt><dd>Copied or Renamed</dd>
   </dl>
  </div>
 </div>

 <form id="prefs" action="<?cs var:browser_current_href ?>" method="get">
  <div>
   <input type="hidden" name="action" value="<?cs var:log.mode ?>" />
   <label for="rev">View log starting from revision:</label>
   <input type="text" id="rev" name="rev" value="<?cs 
    var:log.items.0.rev ?>" size="4" />
   <label for="stop_rev">to:</label>
   <input type="text" id="stop_rev" name="stop_rev" value="<?cs
    var:log.stop_rev ?>" size="4" />
   <br />
   <label for="limit">
    Show at most <input type="text" id="limit" name="limit" 
                        size="2" value="<?cs var:log.limit ?>" /> entries
   </label>
    <fieldset>
     <legend>Mode:</legend>
     <label for="stop_on_copy">
      <input type="radio" id="stop_on_copy" name="log_mode" value="stop_on_copy" <?cs
       if:log.mode != "follow_copy" || log.mode != "path_history" ?> checked="checked" <?cs
       /if ?> />
      Stop on copy 
     </label>
     <label for="follow_copy">
      <input type="radio" id="follow_copy" name="log_mode" value="follow_copy" <?cs
       if:log.mode == "follow_copy" ?> checked="checked" <?cs /if ?> />
      Follow copy operations
     </label>
     <label for="path_history">
      <input type="radio" id="path_history" name="log_mode" value="path_history" <?cs
       if:log.mode == "path_history" ?> checked="checked" <?cs /if ?> />
      Show only add, move and delete operations
     </label>
    </fieldset>
   <label for="full_messages">
    <input type="checkbox" id="full_messages" name="full_messages" <?cs
     if:log.full_messages ?> checked="checked" <?cs /if ?> />
    Show full log messages
   </label>
  </div>
  <div class="buttons">
   <input type="submit" value="Update" 
          title="Warning: by updating, you will clear the page history" />
  </div>
 </form>

 <table id="chglist" class="listing">
  <thead>
   <tr>
    <th class="change"></th>
    <th class="data">Date</th>
    <th class="rev">Rev</th>
    <th class="chgset">Chgset</th>
    <th class="author">Author</th>
    <th class="summary">Log Message</th>
   </tr>
  </thead>
  <tbody><?cs
   set:indent = #1 ?><?cs
   each:item = log.items ?><?cs
    if:item.old_path && !(log.mode == "path" && item.old_path == log.path) ?>
     <tr class="<?cs if:name(item) % #2 ?>even<?cs else ?>odd<?cs /if ?>">
      <td class="old_path" colspan="6" style="padding-left: <?cs var:indent ?>em">
       copied from <a href="<?cs var:item.browser_href ?>"?><?cs var:item.old_path ?></a>:
      </td>
     </tr><?cs
     set:indent = indent + #1 ?><?cs
    elif:log.mode == "path" ?><?cs
      set:indent = #1 ?><?cs
    /if ?>
    <tr class="<?cs if:name(item) % #2 ?>even<?cs else ?>odd<?cs /if ?>">
     <td class="change" style="padding-left:<?cs var:indent ?>em">
      <a title="Examine node history starting from here" href="<?cs var:item.log_href ?>">
       <div class="<?cs var:item.change ?>"></div>
       <span class="comment">(<?cs var:item.change ?>)</span>
      </a>
     </td>
     <td class="date"><?cs var:log.changes[item.rev].date ?></td>
     <td class="rev">
      <a href="<?cs var:item.browser_href ?>"><?cs var:item.rev ?></a>
     </td>
     <td class="chgset">
      <a href="<?cs var:item.changeset_href ?>"><?cs var:item.rev ?></a>
     </td>
     <td class="author"><?cs var:log.changes[item.rev].author ?></td>
     <td class="summary"><?cs var:log.changes[item.rev].message ?></td>
    </tr><?cs
   /each ?>
  </tbody>
 </table>

</div>
<?cs include "footer.cs"?>
