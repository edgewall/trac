<?cs set:html.stylesheet = 'css/changeset.css' ?>
<?cs include "header.cs"?>
<?cs include "macros.cs"?>

<div class="nav">
 <ul class="subheader-links">
  <li class="last"><a href="?format=diff">Download Diff</a></li>
 </ul>
</div>

<div id="main" class="changeset">
<h1>Changeset <?cs var:changeset.revision ?></h1>

<form id="prefs" action="<?cs var:changeset.href ?>">
 <div>
  <label for="type">View differences</label>
  <select name="style">
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
    <input type="checkbox" id="blanklines" name="ignoreblanklines" <?cs
      if:diff.options.ignoreblanklines ?>checked="checked"<?cs /if ?>/>
    <label for="blanklines">Blank lines</label>
   </div>
   <div class="field">
    <input type="checkbox" id="case" name="ignorecase" <?cs
      if:diff.options.ignorecase ?>checked="checked"<?cs /if ?>/>
    <label for="case">Case changes</label>
   </div>
   <div class="field">
    <input type="checkbox" id="whitespace" name="ignorewhitespace" <?cs
      if:diff.options.ignorewhitespace ?>checked="checked"<?cs /if ?>/>
    <label for="whitespace">White space changes</label>
   </div>
  </fieldset>
  <div class="buttons">
   <input type="submit" value="Update" />
  </div>
 </div>
</form>

<dl id="overview">
 <dt class="time">Timestamp:</dt>
 <dd class="time"><?cs var:changeset.time ?></dd>
 <dt class="author">Author:</dt>
 <dd class="author"><?cs var:changeset.author ?></dd>
 <dt class="files">Files:</dt>
 <dd class="files">
  <ul><?cs each:item = changeset.changes ?>
   <li>
    <?cs if:item.change == "A" ?>
     <div class="add"></div>
     <a href="<?cs var:item.browser_href?>" title="Show file in browser"><?cs
       var:item.name ?></a> <span class="comment">(added)</span>
    <?cs elif:item.change == "M" ?>
     <div class="mod"></div>
     <a href="<?cs var:item.browser_href?>" title="Show file in browser"><?cs
       var:item.name ?></a> <span class="comment">(modified)</span>
    <?cs elif:item.change == "D" ?>
     <div class="rem"></div>
     <?cs var:item.name ?> <span class="comment">(deleted)</span>
    <?cs /if ?>
   </li>
  <?cs /each ?></ul>
 </dd>
 <dt class="message">Message:</dt>
 <dd class="message" id="searchable"><?cs var:changeset.message ?></dd>
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
 <ul>
  <?cs each:file = changeset.diff.files ?>
   <?cs if:len(file.changes) ?>
    <li>
     <h2><?cs var:file.name.new ?></h2>
     <?cs if:diff.style == 'sidebyside' ?>
      <table class="sidebyside" summary="Differences">
       <colgroup class="base">
        <col class="lineno" /><col class="content" />
       <colgroup class="chg">
        <col class="lineno" /><col class="content" />
       </colgroup>
       <thead><tr>
        <th colspan="2">Revision <?cs var:file.rev.old ?></th>
        <th colspan="2">Revision <?cs var:file.rev.new ?></th>
       </tr></thead>
       <?cs each:change = file.changes ?>
        <tbody>
         <?cs call:diff_display(change, diff.style) ?>
        </tbody>
        <?cs if:name(change) < len(file.changes) - 1 ?>
         <tbody class="skippedlines">
          <tr><th>&hellip;</th><td>&nbsp;</td><th>&hellip;</th><td>&nbsp;</td></tr>
         </tbody>
        <?cs /if ?>
       <?cs /each ?>
      </table>
     <?cs else ?>
      <table class="inline" summary="Differences">
       <colgroup>
        <col class="lineno" />
        <col class="lineno" />
        <col class="content" />
       </colgroup>
       <thead><tr>
        <th>v<?cs var:file.rev.old ?></th>
        <th>v<?cs var:file.rev.new ?></th>
        <th></th>
       </tr></thead>
       <?cs each:change = file.changes ?>
        <tbody>
         <?cs call:diff_display(change, diff.style) ?>
        </tbody>
        <?cs if:name(change) < len(file.changes) - 1 ?>
         <tbody class="skippedlines">
          <tr><th>&hellip;</th><th>&hellip;</th><td>&nbsp;</td></tr>
         </tbody>
        <?cs /if ?>
       <?cs /each ?>
      </table>
     <?cs /if ?>
    </li>
   <?cs /if ?>
  <?cs /each ?>
 </ul>
</div>

</div>
<?cs include "footer.cs"?>
