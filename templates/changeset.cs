<?cs set:html.stylesheet = 'css/changeset.css' ?>
<?cs include "header.cs"?>
<?cs include "macros.cs"?>


<div id="ctxtnav" class="nav">
 <h2>Changeset Navigation</h2>
 <ul><?cs
  if:len(links.prev) ?>
   <li class="first<?cs if:!len(links.next) ?> last<?cs /if ?>">
    <a class="prev" href="<?cs var:links.prev.0.href ?>" title="<?cs
      var:links.prev.0.title ?>">Previous Changeset</a>
   </li><?cs
  /if ?><?cs
  if:len(links.next) ?>
   <li class="<?cs if:len(links.prev) ?>first <?cs /if ?>last">
    <a class="next" href="<?cs var:links.next.0.href ?>" title="<?cs
      var:links.next.0.title ?>">Next Changeset</a>
   </li><?cs
  /if ?>
 </ul>
</div>

<div id="content" class="changeset">
<h1>Changeset <?cs var:changeset.revision ?></h1>

<?cs each:change = changeset.changes ?><?cs
 if:len(change.diff) ?><?cs
  set:has_diffs = 1 ?><?cs
 /if ?><?cs
/each ?><?cs if:has_diffs || diff.options.ignoreblanklines 
  || diff.options.ignorecase || diff.options.ignorewhitespace ?>
<form method="post" id="prefs" action="">
 <div>
  <label for="style">View differences</label>
  <select id="style" name="style">
   <option value="inline"<?cs
     if:diff.style == 'inline' ?> selected="selected"<?cs
     /if ?>>inline</option>
   <option value="sidebyside"<?cs
     if:diff.style == 'sidebyside' ?> selected="selected"<?cs
     /if ?>>side by side</option>
  </select>
  <div class="field">
   Show <input type="text" name="contextlines" id="contextlines" size="2"
     maxlength="2" value="<?cs var:diff.options.contextlines ?>" />
   <label for="contextlines">lines around each change</label>
  </div>
  <fieldset id="ignore">
   <legend>Ignore:</legend>
   <div class="field">
    <input type="checkbox" id="blanklines" name="ignoreblanklines"<?cs
      if:diff.options.ignoreblanklines ?> checked="checked"<?cs /if ?> />
    <label for="blanklines">Blank lines</label>
   </div>
   <div class="field">
    <input type="checkbox" id="case" name="ignorecase"<?cs
      if:diff.options.ignorecase ?> checked="checked"<?cs /if ?> />
    <label for="case">Case changes</label>
   </div>
   <div class="field">
    <input type="checkbox" id="whitespace" name="ignorewhitespace"<?cs
      if:diff.options.ignorewhitespace ?> checked="checked"<?cs /if ?> />
    <label for="whitespace">White space changes</label>
   </div>
  </fieldset>
  <div class="buttons">
   <input type="submit" name="update" value="Update" />
  </div>
 </div>
</form><?cs /if ?>


<?cs def:node_change(item,cl,kind) ?><?cs 
  set:ndiffs = len(item.diff) ?><?cs
  set:nprops = len(item.props) ?><?cs
  if:$ndiffs + $nprops > #0 && cl != "mod" ?>
    <div class="<?cs var:cl ?>"><div class="mod"></div></div><?cs 
  else ?> 
  <div class="<?cs var:cl ?>"></div><?cs
  /if ?><?cs 
  if:cl == "rem" ?>
   <a title="Show what was removed (rev. <?cs var:item.rev.old ?>)" 
      href="<?cs var:item.browser_href.old ?>"><?cs var:item.name.old ?></a><?cs
  else ?> 
   <a title="Show entry in browser"
      href="<?cs var:item.browser_href.new ?>"><?cs var:item.name.new ?></a><?cs
    /if ?>
     <span class="comment">(<?cs var:kind ?>)</span><?cs
  if:item.copyfrom_path ?>
    &nbsp;<small><em>(<?cs var:kind ?>&nbsp;from&nbsp;<a 
      href="<?cs var:item.browser_href.old ?>" 
      title="Show original file (rev. <?cs var:item.rev.old ?>)"
    ><?cs var:item.copyfrom_path ?></a>)</em></small><?cs
  /if ?><?cs 
  if:$ndiffs + $nprops > #0 ?>
    (<a href="#file<?cs var:name(item) ?>" title="Show differences"><?cs
      if:$ndiffs > #0 ?><?cs var:ndiffs ?>&nbsp;diff<?cs if:$ndiffs > #1 ?>s<?cs /if ?><?cs 
      /if ?><?cs
      if:$ndiffs && $nprops ?>, <?cs /if ?><?cs 
      if:$nprops > #0 ?><?cs var:nprops ?>&nbsp;prop<?cs if:$nprops > #1 ?>s<?cs /if ?><?cs
      /if ?></a>)<?cs
  elif:cl == "mod" ?>
    (<a href="<?cs var:item.browser_href.old ?>"
        title="Show previous version in browser">previous</a>)<?cs
  /if ?>
<?cs /def ?>

<dl id="overview">
 <dt class="time">Timestamp:</dt>
 <dd class="time"><?cs var:changeset.time ?></dd>
 <dt class="author">Author:</dt>
 <dd class="author"><?cs var:changeset.author ?></dd>
 <dt class="message">Message:</dt>
 <dd class="message" id="searchable"><?cs var:changeset.message ?></dd>
 <dt class="files">Files:</dt>
 <dd class="files">
  <ul><?cs each:item = changeset.changes ?>
   <li>
    <?cs if:item.change == "A" ?>
     <?cs call:node_change(item,"add","added") ?>
    <?cs elif:item.change == "D" ?>
     <?cs call:node_change(item,"rem","deleted") ?>
    <?cs elif:item.change == "C" ?>
     <?cs call:node_change(item,"cp","copied") ?>
    <?cs elif:item.change == "R" ?>
     <?cs call:node_change(item,"mv","renamed") ?>
    <?cs elif:item.change == "M" ?>
     <?cs call:node_change(item,"mod","modified") ?>
    <?cs /if ?>
   </li>
  <?cs /each ?></ul>
 </dd>
</dl>

<div class="diff">
 <div id="legend">
  <h3>Legend:</h3>
  <dl>
   <dt class="unmod"></dt><dd>Unmodified</dd>
   <dt class="add"></dt><dd>Added</dd>
   <dt class="rem"></dt><dd>Removed</dd>
   <dt class="mod"></dt><dd>Modified</dd>
  </dl>
  <dl>
   <dt class="cp"></dt><dd>Copied</dd>
   <dt class="mv"></dt><dd>Renamed</dd>
   <dt class="unmod"><div class="mod"></div></dt><dd><em>(... and modified)</em></dd>
  </dl>
 </div>
 <ul class="entries">
  <?cs each:item = changeset.changes ?>
   <?cs if:len(item.diff) || len(item.props) ?>
    <li class="entry" id="file<?cs var:name(item) ?>">
     <h2><a href="<?cs var:item.browser_href.new ?>" 
            title="Show new revision <?cs var:item.rev.new ?> of this file in browser"><?cs
       var:item.name.new ?></a></h2><?cs
     if:len(item.props) ?>
      <ul class="props"><?cs each:prop = item.props ?><li>
       Property <strong><?cs var:name(prop) ?></strong> <?cs
       if:prop.old && prop.new ?>changed from <?cs
       elif:!prop.old ?>set<?cs
       else ?>deleted<?cs
       /if ?><?cs
       if:prop.old && prop.new ?><em><tt><?cs var:prop.old ?></tt></em><?cs /if ?><?cs
       if:prop.new ?> to <em><tt><?cs var:prop.new ?></tt></em><?cs /if ?>
      </li><?cs /each ?></ul><?cs
     /if ?><?cs
     if:len(item.diff) ?>
      <table class="<?cs var:diff.style ?>" summary="Differences" cellspacing="0"><?cs
       if:diff.style == 'sidebyside' ?>
        <colgroup class="base">
         <col class="lineno" /><col class="content" />
        <colgroup class="chg">
         <col class="lineno" /><col class="content" />
        </colgroup>
        <thead><tr>
         <th colspan="2">
          <a href="<?cs var:item.browser_href.old ?>"
             title="Show old rev. <?cs var:item.rev.old ?> of <?cs var:item.name.old ?>"> 
           Revision <?cs var:item.rev.old ?></a></th>
         <th colspan="2">
          <a href="<?cs var:item.browser_href.new ?>"
             title="Show new rev. <?cs var:item.rev.old ?> of <?cs var:item.name.new ?>">
           Revision <?cs var:item.rev.new ?></a></th>
        </tr></thead>
        <?cs each:change = item.diff ?>
         <tbody>
          <?cs call:diff_display(change, diff.style) ?>
         </tbody>
         <?cs if:name(change) < len(item.diff) - 1 ?>
          <tbody class="skippedlines">
           <tr><th>&hellip;</th><td>&nbsp;</td>
           <th>&hellip;</th><td>&nbsp;</td></tr>
          </tbody>
         <?cs /if ?>
        <?cs /each ?><?cs
       else ?>
        <colgroup>
         <col class="lineno" />
         <col class="lineno" />
         <col class="content" />
        </colgroup>
        <thead><tr>
         <th title="Revision <?cs var:item.rev.old ?>">
           <a href="<?cs var:item.browser_href.old ?>" 
              title="Show old rev. <?cs var:item.rev.old ?> of <?cs var:item.name.old ?>">
             r<?cs var:item.rev.old ?></a></th>
         <th title="Revision <?cs var:item.rev.new ?>">
           <a href="<?cs var:item.browser_href.new ?>" 
              title="Show new rev. <?cs var:item.rev.new ?> of <?cs var:item.name.new ?>">
             r<?cs var:item.rev.new ?></a></th>
         <th>&nbsp;</th>
        </tr></thead>
        <?cs each:change = item.diff ?>
         <?cs call:diff_display(change, diff.style) ?>
         <?cs if:name(change) < len(item.diff) - 1 ?>
          <tbody class="skippedlines">
           <tr><th>&hellip;</th><th>&hellip;</th><td>&nbsp;</td></tr>
          </tbody>
         <?cs /if ?>
        <?cs /each ?><?cs
       /if ?>
      </table><?cs
     /if ?>
    </li>
   <?cs /if ?>
  <?cs /each ?>
 </ul>
</div>

</div>
<?cs include "footer.cs"?>
