<?cs include "header.cs"?>
<div id="page-content">
<div id="subheader-links">
<ul class="subheader-links">
  <li class="last"><a href="?format=raw">Raw version</a></li>
</ul>
</div>
 <div id="main">
  <div id="main-content">

  <?cs if file.attachment_parent ?>

    <h3>Attachment</h3>
    <a href="<?cs var:file.attachment_parent_href ?>">
    <?cs var:file.attachment_parent ?></a>: <?cs var:file.filename ?>

  <?cs else ?>

    <div id="browser-pathlinks">
      <?cs each:part=file.path ?>
      <a href="<?cs var:part.url ?>"><?cs var:part?></a> /
      <?cs /each ?>
      <?cs var:file.filename ?>
    </div>

  <?cs /if ?>
  <?cs if file.highlighted_html ?>
    <?cs var:file.highlighted_html ?>
  <?cs else ?>
    <hr />
    Html preview unavailable. Click
    <a href="?format=raw">here</a> for raw version.
  <?cs /if ?>

  <?cs if $file.max_file_size_reached ?>
    <div id="main-footer">
     Note: File truncated, only the first <?cs var:$file.max_file_size  ?>
     bytes displayed.
    </div>
  <?cs /if ?>
 </div>
</div>
</div>
<?cs include:"footer.cs"?>

