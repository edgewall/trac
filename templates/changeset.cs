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

<table id="overview" summary="Changeset overview">
 <tr class="time">
  <th scope="row">Timestamp:</th>
  <td><?cs var:changeset.time ?></td>
 </tr>
 <tr class="author">
  <th scope="row">Author:</th>
  <td><?cs var:changeset.author ?></td>
 </tr>
 <tr class="files">
  <th scope="row">Files:</th>
  <td>
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
  </td>
 </tr>
 <tr class="message">
  <th scope="row">Message:</th>
  <td id="searchable"><?cs var:changeset.message ?></td>
 </tr>
</table>

<form id="prefs" action="<?cs var:changeset.href ?>">
 <div>
  <label for="type">View differences</label>
  <select name="style">
   <option value="inline"<?cs
     if:changeset.style == 'inline' ?> selected="selected"<?cs
     /if ?>>inline</option>
   <option value="sidebyside"<?cs
     if:changeset.style == 'sidebyside' ?> selected="selected"<?cs
     /if ?>>side by side</option>
  </select>
  <div class="field">
   Show <input type="text" name="contextlines" id="contextlines" size="2"
     maxlength="2" value="<?cs var:changeset.options.contextlines ?>" />
   <label for="contextlines">lines around each change</label>
  </div>
  <fieldset id="ignore">
   <legend>Ignore:</legend>
   <div class="field">
    <input type="checkbox" id="blanklines" name="ignoreblanklines" <?cs
      if:changeset.options.ignoreblanklines ?>checked="checked"<?cs /if ?>/>
    <label for="blanklines">Blank lines</label>
   </div>
   <div class="field">
    <input type="checkbox" id="case" name="ignorecase" <?cs
      if:changeset.options.ignorecase ?>checked="checked"<?cs /if ?>/>
    <label for="case">Case changes</label>
   </div>
   <div class="field">
    <input type="checkbox" id="whitespace" name="ignorewhitespace" <?cs
      if:changeset.options.ignorewhitespace ?>checked="checked"<?cs /if ?>/>
    <label for="spacechanges">White space changes</label>
   </div>
  </fieldset>
  <div class="buttons">
   <input type="submit" value="Update" />
  </div>
 </div>
</form>

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
     <?cs if:changeset.style == 'sidebyside' ?>
      <table class="sidebyside">
       <thead class="rev"><tr>
        <th colspan="2">Rev <?cs var:file.rev.old ?></th>
        <th colspan="2">Rev <?cs var:file.rev.new ?></th>
       </tr></thead>
       <?cs each:change = file.changes ?>
        <tbody>
         <?cs call:diff_display(change, changeset.style) ?>
        </tbody>
        <?cs if:name(change) < len(file.changes) - 1 ?>
         <tbody class="skippedlines">
          <tr><th>&hellip;</th><td>&nbsp;</td><th>&hellip;</th><td>&nbsp;</td></tr>
         </tbody>
        <?cs /if ?>
       <?cs /each ?>
      </table>
     <?cs else ?>
      <table class="inline">
       <thead class="rev"><tr>
        <th>Rev <?cs var:file.rev.old ?></th>
        <th>Rev <?cs var:file.rev.new ?></th>
        <th></th>
       </tr></thead>
       <?cs each:change = file.changes ?>
        <tbody>
         <?cs call:diff_display(change, changeset.style) ?>
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
