<?cs include "header.cs"?>
<?cs include "macros.cs"?>

<div class="nav">
 <ul class="subheader-links">
  <li class="last"><a href="?format=diff">Download Diff</a></li>
 </ul>
</div>

<div id="main" class="changeset">
<h1 id="chg-hdr">Change set <?cs var:changeset.revision ?></h1>

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

<div class="diff">
 <div class="hide">
   <hr />
   <h2>-=&gt; Note: Diff viewing requires CSS2 &lt;=-</h2>
   <p>Output below might not be useful.</p>
   <hr />
 </div>
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
   <li>
    <h2><?cs var:file.name.new ?></h2>
    <table cellspacing="0">
      <thead class="rev"><tr>
       <th>Rev <?cs var:file.rev.old ?></th>
       <th>Rev <?cs var:file.rev.new ?></th>
      </tr></thead>
     <?cs each:change = file.changes ?>
      <thead><tr>
       <th>line <?cs var:change.line.old ?></th>
       <th>line <?cs var:change.line.new ?></th>
      </tr></thead>
      <tbody>
       <?cs call:diff_display(change) ?>
      </tbody>
     <?cs /each ?>
    </table>
   </li>
  <?cs /each ?>
 </ul>
</div>

</div>
<?cs include:"footer.cs"?>
