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

<?cs def:browser_path_links(path, file) ?><?cs
 set:first = #1 ?>
 <h1><?cs
  each:part=path ?><a <?cs 
   if:first ?>class="first" title="Go to root directory" <?cs 
    set:first = #0 ?><?cs 
   else ?>title="Go to directory" <?cs
   /if ?>href="<?cs var:part.url ?>"><?cs var:part ?></a><?cs
   if:!part.last ?><span class="sep">/</span><?cs
   /if ?><?cs 
 /each ?><?cs
 if:file.filename ?><span class="filename"><?cs var:file.filename ?></span><?cs
 /if ?></h1>
<?cs /def ?>

<?cs def:diff_display(change) ?>
 <?cs each:block = change.blocks ?><tr>
  <td class="<?cs var:block.type ?> left"><?cs
   if:block.type == 'rem' || block.type == 'mod' ?><del><?cs
    var:block.text.old ?></del><?cs
   else ?><?cs
    var:block.text.old ?><?cs
   /if ?></td>
  <td class="<?cs var:block.type ?> right"><?cs
   if:block.type == 'add' || block.type == 'mod' ?><ins><?cs
    var:block.text.new ?></ins><?cs
   else ?><?cs
    var:block.text.new ?><?cs
   /if ?></td>
 </tr><?cs /each ?>
<?cs /def ?>

<?cs def:session_name_email() ?><?cs
  if trac.authname != "anonymous" ?><?cs 
     var:trac.authname ?><?cs 
  elif trac.session.var.name && trac.session.var.email ?><?cs
     var:trac.session.var.name ?> &lt;<?cs var:trac.session.var.email ?>&gt;<?cs 
  elif !trac.session.var.name && trac.session.var.email ?><?cs 
     var:trac.session.var.email ?><?cs 
  else ?><?cs
     var:trac.authname ?><?cs 
  /if ?><?cs
  /def ?>

<?cs def:ticket_custom_props(ticket) ?>
<?cs if ticket.custom.0.name ?>
 <fieldset style="clear: both">
  <legend>Custom Properties</legend>
  <?cs each c=ticket.custom ?>
   <div class="custom-prop">
    <?cs if c.type == 'text' || c.type == 'select' ?>
     <label for="custom_<?cs var c.name ?>">
      <?cs alt c.label ?><?cs var c.name ?><?cs /alt ?></label>: 
    <?cs /if ?>
    <?cs if c.type == 'text' ?>
     <input type="text" id="custom_<?cs var c.name ?>" 
            name="custom_<?cs var c.name ?>" value="<?cs var c.value ?>" />
    <?cs elif c.type == 'textarea' ?>
     <label for="custom_<?cs var c.name ?>">
      <?cs alt c.label ?><?cs var c.name ?><?cs /alt ?></label>:<br />
    <textarea
      cols="<?cs alt c.width ?>60<?cs /alt ?>" 
      rows="<?cs alt c.height ?>12<?cs /alt ?>"
      name="custom_<?cs var c.name ?>"><?cs var c.value ?></textarea>
    <?cs elif c.type == 'checkbox' ?>
     <input type="hidden" name="checkbox_<?cs var c.name ?>" 
            value="custom_<?cs var c.name ?>" />
     <input type="checkbox" id="custom_<?cs var c.name ?>" 
            name="custom_<?cs var c.name ?>" 
            value="1"
            <?cs if c.selected ?>checked="checked"<?cs /if ?> />
     <label for="custom_<?cs var c.name ?>">
      <?cs alt c.label ?><?cs var c.name ?><?cs /alt ?></label>
    <?cs elif c.type == 'select' ?>
     <select name="custom_<?cs var c.name ?>">
      <?cs each v=c.option ?>
       <option <?cs if v.selected ?>selected="selected"<?cs /if ?>>
        <?cs var v ?>
       </option>
      <?cs /each ?>
     </select>
    <?cs elif c.type == 'radio' ?>
      <?cs each v=c.option ?>
       <input type="radio" name="custom_<?cs var c.name ?>" 
         <?cs if v.selected ?>checked="checked"<?cs /if ?> 
            value="<?cs var v ?>" id="<?cs var v ?>"/>
       <label for="<?cs var v ?>">
        <?cs var v ?></label><br />
      <?cs /each ?>
    <?cs /if ?>
   </div>
  <?cs /each ?>
 </fieldset>
<?cs /if ?>
<?cs /def ?>

<?cs def:wiki_tool(textarea, infobox, img, alt, beg, end, example) ?>
  addButton('<?cs var:textarea ?>', '<?cs var:infobox ?>', 
            '<?cs var:$htdocs_location + '/' + $img ?>', '<?cs var:alt ?>',
            '<?cs var:beg ?>','<?cs var:end ?>','<?cs var:example ?>');
<?cs /def ?>

<?cs def:wiki_toolbar(textarea) ?>
<script type='text/javascript'>
/*<![CDATA[*/
<?cs set:infobox='wiki-info-' + $textarea ?>
  document.writeln("<div id='wiki-toolbar'>");
  <?cs call:wiki_tool($textarea, $infobox, 'edit_bold.png', 'Bold text',
                      "\'\'\'", "\'\'\'", 'Bold text') ?>
  <?cs call:wiki_tool($textarea, $infobox, 'edit_italic.png', 'Italic text',
                      "\'\'","\'\'", 'Italic text') ?>
  <?cs call:wiki_tool($textarea, $infobox, 'edit_link.png', 'Link',
                      '[', ']', 'http://example.com/ Link Title') ?>
  <?cs call:wiki_tool($textarea, $infobox, 'edit_hdr.png', 'Headline',
                      '\n== ', ' ==\n', 'Headline text') ?>
  <?cs call:wiki_tool($textarea, $infobox, 'edit_block.png', 'Code Block',
                      '\n{{{\n ', '\n}}}\n', 'Preformatted block' ) ?>
  <?cs call:wiki_tool($textarea, $infobox, 'edit_hr.png', 'Horizontal Rule',
                      '\n----\n','','') ?>
  document.writeln("</div>");
  addInfobox('<?cs var:infobox ?>', 'Click a button to get an example text',
             'Please enter the text you want to be formatted.\\n It will be shown in the infobox for copy and pasting.\\nExample:\\n$1\\nwill become:\\n$2');
/*]]>*/
</script>
<?cs /def ?>
