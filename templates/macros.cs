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

<?cs def:diff_display(change, style) ?><?cs
 if:style == 'sidebyside' ?><?cs
  each:block = change.blocks ?><?cs
   if:block.type == 'unmod' ?><?cs
    each:line = block.base.lines ?><tr class="unmod">
     <th class="base"><?cs var:#block.base.offset + name(line) ?></th>
     <td class="base"><span><?cs var:line ?></span></td>
     <th class="chg"><?cs var:#block.changed.offset + name(line) ?></th>
     <td class="chg"><span><?cs var:line ?></span></td>
    </tr><?cs /each ?><?cs
   elif:block.type == 'mod' ?><?cs
    if:len(block.base.lines) >= len(block.changed.lines) ?><?cs
     each:line = block.base.lines ?><tr class="mod">
      <th class="base"><?cs var:#block.base.offset + name(line) ?></th>
      <td class="base"><del><?cs var:line ?></del></td><?cs
      if:len(block.changed.lines) >= name(line) ?><?cs
       each:changedline = block.changed.lines ?><?cs
        if:name(changedline) == name(line) ?>
         <th class="chg"><?cs var:#block.changed.offset + name(changedline) ?></th>
         <td class="chg"><ins><?cs var:changedline ?></ins></td><?cs
        /if ?><?cs
       /each ?><?cs
      else ?>
       <th class="chg"></th>
       <td class="chg"></td><?cs
      /if ?>
     </tr><?cs /each ?><?cs
    else ?><?cs
     each:line = block.changed.lines ?><tr class="mod"><?cs
      if:len(block.base.lines) >= name(line) ?><?cs
       each:baseline = block.base.lines ?><?cs
        if:name(baseline) == name(line) ?>
         <th class="base"><?cs var:#block.base.offset + name(baseline) ?></th>
         <td class="base"><del><?cs var:baseline ?></del></td><?cs
        /if ?><?cs
       /each ?><?cs
      else ?>
       <th class="base"></th>
       <td class="base"></td><?cs
      /if ?>
      <th class="chg"><?cs var:#block.changed.offset + name(line) ?></th>
      <td class="chg"><ins><?cs var:line ?></ins></td>
     </tr><?cs /each ?><?cs
    /if ?><?cs
   elif:block.type == 'add' ?><?cs
    each:line = block.changed.lines ?><tr class="add">
     <th class="base">&nbsp;</th>
     <td class="base">&nbsp;</td>
     <th class="chg"><?cs var:#block.changed.offset + name(line) ?></th>
     <td class="chg"><ins><?cs var:line ?></ins></td>
    </tr><?cs /each ?><?cs
   elif:block.type == 'rem' ?><?cs
    each:line = block.base.lines ?><tr class="rem">
     <th class="base"><?cs var:#block.base.offset + name(line) ?></th>
     <td class="base"><del><?cs var:line ?></del></td>
     <th class="chg">&nbsp;</th>
     <td class="chg">&nbsp;</td>
    </tr><?cs /each ?><?cs
   /if ?><?cs
  /each ?><?cs
 else ?><?cs
  each:block = change.blocks ?><?cs
   if:block.type == 'unmod' ?><?cs
    each:line = block.base.lines ?><tr class="unmod">
     <th class="base"><?cs var:#block.base.offset + name(line) ?></th>
     <th class="chg"><?cs var:#block.changed.offset + name(line) ?></th>
     <td class="base"><span><?cs var:line ?></span></td>
    </tr><?cs /each ?><?cs
   elif:block.type == 'mod' ?><?cs
    each:line = block.base.lines ?><tr class="mod<?cs
      if:name(line) == 1 ?> first<?cs /if ?>">
     <th class="base"><?cs var:#block.base.offset + name(line) ?></th>
     <th class="chg">&nbsp;</th>
     <td class="base"><del><?cs var:line ?></del></td>
    </tr><?cs /each ?><?cs
    each:line = block.changed.lines ?><tr class="mod<?cs
      if:name(line) == len(block.changed.lines) ?> last<?cs /if ?>">
     <th class="base">&nbsp;</th>
     <th class="chg"><?cs var:#block.changed.offset + name(line) ?></th>
     <td class="chg"><ins><?cs var:line ?></ins></td>
    </tr><?cs /each ?><?cs
   elif:block.type == 'add' ?><?cs
    each:line = block.changed.lines ?><tr class="add<?cs
      if:name(line) == 1 ?> first<?cs /if ?><?cs
      if:name(line) == len(block.changed.lines) ?> last ?><?cs /if ?>">
     <th class="base">&nbsp;</th>
     <th class="chg"><?cs var:#block.changed.offset + name(line) ?></th>
     <td class="chg"><ins><?cs var:line ?></ins></td>
    </tr><?cs /each ?><?cs
   elif:block.type == 'rem' ?><?cs
    each:line = block.base.lines ?><tr class="rem<?cs
      if:name(line) == 1 ?> first<?cs /if ?><?cs
      if:name(line) == len(block.base.lines) ?> last ?><?cs /if ?>">
     <th class="base"><?cs var:#block.base.offset + name(line) ?></th>
     <th class="chg">&nbsp;</th>
     <td class="base"><del><?cs var:line ?></del></td>
    </tr><?cs /each ?><?cs
   /if ?><?cs
  /each ?><?cs
 /if ?><?cs
/def ?>

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
