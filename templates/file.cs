<?cs include "header.cs"?>
<?cs include "macros.cs"?>
<div id="page-content">
<div id="subheader-links">
<ul class="subheader-links">
  <?cs if args.mode!= 'attachment' ?>
  <li><a href="<?cs var:file.logurl ?>">Revision Log</a></li>
  <?cs /if ?>
  <li><a href="<?cs var:file.texturl ?>">View as Text</a></li>
  <li class="last"><a href="<?cs var:file.rawurl ?>">Download File</a></li>
</ul>
</div>
 <div id="main">
  <div id="main-content">

  <?cs if file.attachment_parent ?>

    <h1><a href="<?cs var:file.attachment_parent_href ?>">
    <?cs var:file.attachment_parent ?></a>: <?cs var:file.filename ?></h1>
    <div id="browser-nav">
    <ul class="menulist">
      <li><a title="Show file as plaintext" 
       href="<?cs var:file.texturl ?>">View as Text</a></li>
      <li><a title="Download this revision" 
          href="<?cs var:file.rawurl ?>">Download File</a></li>
      <?cs if $trac.acl.TRAC_ADMIN ?>
      <li><a title="Delete This Attachment" 
          href="?delete=yes">Delete Attachment</a></li>
      <?cs /if ?>
      </ul>
    <div class="tiny" style="clear: both">&nbsp;</div>
    </div>
  <?cs else ?>
    <h1 id="file-hdr" class="hide"><?cs var:file.filename ?></h1>
    <?cs call:browser_path_links(file.path, file) ?>
    <div id="browser-nav">
    <ul class="menulist"><li><a 
      title="View Revision Log" 
       href="<?cs var:file.logurl ?>">Revision Log</a></li><li><a 
      title="Show file as plaintext" 
       href="<?cs var:file.texturl ?>">View as Text</a></li><li class="last"><a 
      title="Download this revision"  
       href="<?cs var:file.rawurl ?>">Download File</a></li></ul>
    <form id="browser-chgrev" action="" method="get">
     <div>
      <label for="rev">View rev:</label>
      <input type="text" id="rev" name="rev" value="<?cs
        var:file.rev ?>" size="4" />
      <input type="submit" value="View"/>
     </div>
    </form>
    <div class="tiny" style="clear: both">&nbsp;</div>
    </div>
  
   <div id="revinfo">
     <h2>Revision <a href="<?cs var:file.chgset_href ?>"><?cs var:file.rev ?></a> (by <?cs var:file.rev_author ?>, <?cs var:file.rev_date ?>)</h2>
     <div id="revchange"><?cs var:file.rev_msg ?></div>
    <div class="tiny" style="clear: both">&nbsp;</div>
   </div>

  <?cs /if ?>
  <?cs if file.highlighted_html ?>
    <?cs var:file.highlighted_html ?>
  <?cs else ?>
    <div class="code-block">
    Html preview unavailable. To view, 
    <a href="<?cs var:file.filename+'?rev='+file.rev ?>&format=raw">download
    the file</a>.
    </div>
  <?cs /if ?>

  <?cs if $file.max_file_size_reached ?>
    <div id="main-footer">
     <b>Note:</b> HTML preview not available, since file-size exceeds <?cs var:$file.max_file_size  ?> bytes.
         Try <a href="?format=raw">downloading the file</a> instead.
    </div>
  <?cs /if ?>
 </div>
</div>
</div>
<?cs include:"footer.cs"?>

