<?cs include "header.cs"?>
<?cs include "macros.cs"?>
<div id="page-content">
 <ul class="subheader-links">
   <li><a href="?format=diff">Download Diff</a></li>
 </ul>
 <div id="main">
  <div id="main-content">

<h1 id="chg-hdr">Change set <?cs var:changeset.revision ?></h1>

<div id="chg-preface">
  <div id="chg-info">
  <div>
    <b class="chg-name">Revision:</b>
    <span class="chg-val"><?cs var:changeset.revision ?></span>
  </div>
  <div>
    <b class="chg-name">Timestamp:</b>
    <span class="chg-val"><?cs var:changeset.time ?></span>
  </div>
  <div>
    <b class="chg-name">Author:</b>
    <span class="chg-val"><?cs var:changeset.author ?></span>
  </div>
  <div>
    <b class="chg-name">Message:</b>
    <div class="chg-val"><div id="searchable"><?cs var:changeset.message ?></div></div>
  </div>
  </div>
    <div id="chg-files">
    <b>Files:</b>
    <ul>
      <?cs each:item = changeset.changes ?>
        <li>
          <?cs if item.change == "A" ?>
            <span  class="chg-file-add"> </span>
            <a href="<?cs var:item.browser_href?>"><?cs var:item.name ?></a>
            <span class="chg-file-comment">(added)</span>
          <?cs elif item.change == "M" ?>
            <span  class="chg-file-mod"> </span>
            <a href="<?cs var:item.browser_href?>"><?cs var:item.name ?></a>
            <span class="chg-file-comment">(modified)</span>
          <?cs elif item.change == "D" ?>
            <span  class="chg-file-rem"> </span>
            <?cs var:item.name ?>
          <span class="chg-file-comment">(deleted)</span>
          <?cs /if ?>
          <div class="tiny"><br /></div>
        </li>
      <?cs /each ?>
    </ul>
   </div>
 <br style="clear: both" /><div class="tiny">&nbsp;</div>
</div> 

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
