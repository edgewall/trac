<?cs def:hdf_select(enum, name, selected) ?>
  <select size="1" id="<?cs var:name ?>" name="<?cs var:name ?>">
  <?cs each:item = $enum ?>
    <?cs if item.name == $selected ?>
      <option selected="selected"><?cs var:item.name ?></option>
    <?cs else ?>
      <option><?cs var:item.name ?></option>
    <?cs /if ?>
  <?cs /each ?>
  </select>
<?cs /def?>

<?cs def:browser_path_links(path, file) ?>
<?cs set:first=#1 ?>
<div id="browser-pathlinks"><?cs 
   each:part=path ?><a <?cs 
     if:first ?>class="first" title="Go to root directory"<?cs 
         set:first=#0  ?><?cs 
     /if ?>
     href="<?cs var:part.url ?>"><?cs var:part ?></a><?cs
   if:!part.last ?><span class="browser-pathsep">/</span><?cs /if ?><?cs 
 /each ?><?cs if:file.filename ?><span class="filename"><?cs var:file.filename
 ?></span><?cs /if ?></div>
<?cs /def ?>

<?cs def:diff_display(change) ?>
 <?cs each:block = change.blocks ?><tr>
  <td class="<?cs var:block.type ?> left"><?cs var:block.text.old ?></td>
  <td class="<?cs var:block.type ?> right"><?cs var:block.text.new ?></td>
 </tr><?cs /each ?>
<?cs /def ?>

<?cs def:session_name_email() ?>
<?cs var:trac.session.var.name ?><?cs 
  if:trac.session.var.email ?><?cs 
    if:trac.session.var.name ?> &lt;<?cs var:trac.session.var.email ?>&gt;<?cs 
    else ?><?cs var:trac.session.var.email ?><?cs 
    /if ?><?cs 
  /if ?><?cs 
  if:!trac.session.var.name && !trac.session.var.email ?><?cs
     var:trac.authname ?><?cs 
  /if ?>
<?cs /def ?>
