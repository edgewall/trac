<?cs set:html.stylesheet = 'css/browser.css' ?>
<?cs include "header.cs"?>
<?cs include "macros.cs"?>

<div class="nav">
 <ul class="subheader-links">
  <?cs if args.mode!= 'attachment' ?>
  <li><a href="<?cs var:file.logurl ?>">Revision Log</a></li>
  <?cs /if ?>
  <li><a href="<?cs var:file.texturl ?>">View as Text</a></li>
  <li class="last"><a href="<?cs var:file.rawurl ?>">Download File</a></li>
 </ul>
</div>

<div id="main" class="file">

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
   <?cs call:browser_path_links(file.path, file) ?>
   <div id="toolbar">
    <ul>
     <li><a title="View revision log" href="<?cs
       var:file.logurl ?>">Revision Log</a></li>
     <li><a title="Show file as plain text" href="<?cs
       var:file.texturl ?>">View as Text</a></li>
     <li class="last"><a title="Download this revision" href="<?cs
       var:file.rawurl ?>">Download File</a></li>
    </ul>
    <form action="" method="get">
     <div>
      <label for="rev">View rev:</label>
      <input type="text" id="rev" name="rev" value="<?cs
        var:file.rev ?>" size="4" />
      <input type="submit" value="View"/>
     </div>
    </form>
   </div>
  
   <table id="info" summary="Revision info">
    <tr>
     <th scope="row">
      Revision <a href="<?cs var:file.chgset_href ?>"><?cs var:file.rev ?></a>
      (by <?cs var:file.rev_author ?>, <?cs var:file.rev_date ?>)
     </th>
     <td class="message"><?cs var:file.rev_msg ?></td>
    </tr>
   </table>

  <?cs /if ?>

  <div id="content">
   <?cs if:file.highlighted_html ?>
    <?cs var:file.highlighted_html ?>
   <?cs elif:file.max_file_size_reached ?>
    <strong>HTML preview not available</strong>, since file-size exceeds
    <?cs var:file.max_file_size  ?> bytes.
    Try <a href="?format=raw">downloading the file</a> instead.
   <?cs else ?>
    <strong>HTML preview not available</strong>. To view, <a href="<?cs
    var:file.filename + '?rev=' + file.rev ?>&format=raw">download the
    file</a>.
   <?cs /if ?>
  </div>

</div>

<?cs include "footer.cs"?>
