<?cs include "header.cs"?>
<?cs include "macros.cs"?>
<div id="page-content">
 <ul class="subheader-links">
   <li class="last"><a href="?format=diff">Download Diff</a></li>
 </ul>
 <div id="main" class="changeset">
  <div id="main-content">

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
      <span class="chg-file-add"> </span>
      <a href="<?cs var:item.browser_href?>" title="Show file in browser"><?cs
        var:item.name ?></a> <span class="comment">(added)</span>
     <?cs elif:item.change == "M" ?>
      <span class="chg-file-mod"> </span>
      <a href="<?cs var:item.browser_href?>" title="Show file in browser"><?cs
        var:item.name ?></a> <span class="comment">(modified)</span>
     <?cs elif:item.change == "D" ?>
      <span class="chg-file-rem"> </span>
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

<div class="hide">
  <hr class="hide" />
  <h2>-=&gt; Note: Diff viewing requires CSS2 &lt;=-</h2>
  <p>
    Output below might not be useful.
  </p>
  <hr class="hide" />
</div>

<div id="chg-legend">
  <h3>Legend:</h3>
  <ul>
    <li><span class="diff-legend-unmod"> </span>Unmodified</li>
    <li><span class="diff-legend-add"> </span>Added</li>
    <li><span class="diff-legend-rem"> </span>Removed</li>
    <li><span class="diff-legend-mod"> </span>Modified</li>
   </ul>
</div>

<div id="chg-diff">
  <?cs each:file = changeset.diff.files ?>
    <div class="chg-diff-file">
      <h3 class="chg-diff-hdr"><?cs var:file.name.new ?></h3>
      <table class="diff-table" cellspacing="0">
        <?cs each:change = file.changes ?>
          <tr><td class="diff-line">line <?cs var:change.line.old ?></td>
          <td class="diff-line">line <?cs var:change.line.new ?></td></tr>
          <?cs call:diff_display(change) ?>
        <?cs /each ?>
      </table>
    </div>
  <?cs /each ?>
</div>

 <div id="main-footer">
  Download in other formats: <br />
  <a href="?format=diff">Unified Diff</a>
  <br />
 </div>

 </div>
</div>
</div>
<?cs include:"footer.cs"?>
