<?cs set:html.stylesheet = 'css/code.css' ?>
<?cs include "header.cs" ?>
<?cs include "macros.cs" ?>

<div id="ctxtnav" class="nav"></div>

<div id="content" class="attachment">

 <h3>Add Attachment to <a href="<?cs
   var:file.attachment_parent_href?>"><?cs var:file.attachment_parent?></a></h3>
 <fieldset>
  <form action="<?cs var:cgi_location ?>" method="post" 
        enctype="multipart/form-data">
   <input type="hidden" name="mode" value="attachment" />
   <input type="hidden" name="type" value="<?cs var:attachment.type ?>" />
   <input type="hidden" name="id"   value="<?cs var:attachment.id ?>" />
   <div style="align: right">
    <label for="author" class="att-label">Author:</label>
    <input type="text" id="author" name="author" class="textwidget" size="40"
        value="<?cs var:attachment.author?>" />
    <br />
    <label for="description" class="att-label">Description:</label>
    <input type="text" id="description" name="description" class="textwidget"
        size="40" />
    <br />
    <label for="file" class="att-label">File:</label>
    <input type="file" id="file" name="attachment" />
    <br />
    <br />
    <input type="reset" value="Reset" />
    <input type="submit" value="Add" />
   </div>
  </form>
 </fieldset>

</div>
<?cs include "footer.cs"?>
