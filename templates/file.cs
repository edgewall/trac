<?cs include "header.cs"?>
<?cs include "macros.cs"?>
<?cs set:file.rawurl = file.url + '&format=raw' ?>
<?cs set:file.texturl = file.url + '&format=text' ?>
<div id="page-content">
<div id="subheader-links">
<ul class="subheader-links">
  <li class="last"><a href="<?cs var:file.logurl ?>">Revision Log</a></li>
  <li><a href="<?cs var:file.texturl ?>">View as Text</a></li>
  <li><a href="<?cs var:file.rawurl ?>">Download File</a></li>
</ul>
</div>
 <div id="main">
  <div id="main-content">

  <?cs if file.attachment_parent ?>

    <h3>Attachment</h3>
    <a href="<?cs var:file.attachment_parent_href ?>">
    <?cs var:file.attachment_parent ?></a>: <?cs var:file.filename ?>

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
        <label for="rev">View rev:</label><input
        type="text" id="rev" name="rev" value="<?cs var:file.rev ?>"
          size="4" />
        <input type="submit" value="View"/>
      </div>
    </form>
    <div class="tiny" style="clear: both">&nbsp;</div>
    </div>
  <?cs /if ?>
  <?cs if file.highlighted_html ?>
    <?cs var:file.highlighted_html ?>
  <?cs else ?>
    <hr />
    Html preview unavailable. Click
    <a href="<a href="<?cs var:file.filename+'?rev='+file.rev ?>&format=raw">here</a> for raw version.
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

