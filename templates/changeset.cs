<?cs include "header.cs"?>
<div id="page-content">
 <div id="subheader-links">
 </div>
 <div id="main">
  <div id="main-content">

<h1 id="chg-hdr">Change set <?cs var:changeset.revision ?></h1>

<div class="chg-preface">
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
    <div class="chg-val"><?cs var:changeset.message ?></div>
    <b class="chg-name">Files:</b>
    <ul class="chg-list">
      <?cs each:item = changeset.changes ?>
        <li>
          <?cs if item.change == "A" ?>
            <span  class="chg-file-add"> </span>
            <a href="<?cs var:item.log_href?>"><?cs var:item.name ?></a>
            <span class="chg-file-comment">(added)</span>
          <?cs elif item.change == "M" ?>
            <span  class="chg-file-mod"> </span>
            <a href="<?cs var:item.log_href?>"><?cs var:item.name ?></a>
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
</div> 

<div class="hide">
  <hr class="hide" />
  <h2>-=&gt; Note: Diff viewing requires CSS2 &lt;=-</h2>
  <p>
    Output below might not be useful.
  </p>
  <hr class="hide" />
</div>    
    
<div id="chg-diff">
  <div id="chg-legend">
    <h3>Legend</h3>
    <span class="diff-legend-add"> </span>Added 
    <div class="tiny"><br /></div>
    <span class="diff-legend-rem"> </span>Removed
    <div class="tiny"><br /></div>
    <span class="diff-legend-mod"> </span>Modified
    <div class="tiny"><br /></div>
    <span class="diff-legend-unmod"> </span>Unmodified
    <div class="tiny"><br /></div>
  </div>

  <?cs var:changeset.diff_output ?>
</div>

 </div>
</div>
</div>
<?cs include:"footer.cs"?>
