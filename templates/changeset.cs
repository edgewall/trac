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
/each ?><?cs if:has_diffs ?>
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
     <div class="add"></div>
     <a href="<?cs var:item.browser_href.new ?>" title="Show file in browser"><?cs
       var:item.name ?></a> <span class="comment">(added)</span>
    <?cs elif:item.change == "M" ?>
     <div class="mod"></div>
     <a href="<?cs var:item.browser_href.new ?>" title="Show file in browser"><?cs
       var:item.name ?></a> <span class="comment">(modified)</span><?cs
     if:len(item.diff) || len(item.props) ?>
      (<a href="#file<?cs var:name(item) ?>" title="Show differences">diff</a>)<?cs
     /if ?>
    <?cs elif:item.change == "D" ?>
     <div class="rem"></div>
     <?cs var:item.name ?> <span class="comment">(deleted)</span>
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
 </div>
 <ul class="entries">
  <?cs each:item = changeset.changes ?>
   <?cs if:len(item.diff) || len(item.props) ?>
    <li class="entry" id="file<?cs var:name(item) ?>">
     <h2><a href="<?cs
       var:item.browser_href.new ?>" title="Show version <?cs
       var:item.rev.new ?> of this file in browser"><?cs
       var:item.name ?></a></h2><?cs
     if:len(item.props) ?>
      <ul class="props"><?cs each:prop = item.props ?><li>
       Property <strong><?cs var:name(prop) ?></strong> <?cs
       if:prop.old && prop.new ?>changed from <?cs
       elif:!prop.old ?>set<?cs
       else ?>deleted<?cs
       /if ?><?cs
       if:prop.old && prop.new ?><em><?cs var:prop.old ?></em><?cs /if ?><?cs
       if:prop.new ?> to <em><?cs var:prop.new ?></em><?cs /if ?>
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
         <th colspan="2"><a href="<?cs var:item.browser_href.old ?>">Revision <?cs
           var:item.rev.old ?></a></th>
         <th colspan="2"><a href="<?cs var:item.browser_href.new ?>">Revision <?cs
           var:item.rev.new ?></a></th>
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
         <th title="Revision <?cs var:item.rev.old ?>"><a href="<?cs
           var:item.browser_href.old ?>" title="Show revision <?cs
           var:item.rev.old ?> of this file in browser">r<?cs
           var:item.rev.old ?></a></th>
         <th title="Revision <?cs var:item.rev.new ?>"><a href="<?cs
           var:item.browser_href.new ?>" title="Show revision <?cs
           var:item.rev.new ?> of this file in browser">r<?cs
           var:item.rev.new ?></a></th>
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
