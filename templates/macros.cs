<?cs def:hdf_select(options, name, selected, optional) ?>
 <select size="1" id="<?cs var:name ?>" name="<?cs var:name ?>"><?cs
  if:optional ?><option></option><?cs /if ?><?cs
  each:option = options ?><?cs
   if option.name == $selected ?>
    <option selected="selected"><?cs var:option.name ?></option><?cs
   else ?>
    <option><?cs var:option.name ?></option><?cs
   /if ?><?cs
  /each ?>
 </select><?cs
/def?>

<?cs def:browser_path_links(path, file) ?><?cs
 set:first = #1 ?>
 <h1><?cs
  each:part = path ?><?cs
   set:last = name(part) == len(path) - #1 ?><a<?cs 
   if:first ?> class="first" title="Go to root directory"<?cs 
    set:first = #0 ?><?cs 
   else ?> title="Go to directory"<?cs
   /if ?> href="<?cs var:part.url ?>"><?cs var:part ?></a><?cs
   if:file.filename || !last ?><span class="sep">/</span><?cs /if ?><?cs 
 /each ?><?cs
 if:file.filename ?><span class="filename"><?cs var:file.filename ?></span><?cs
 /if ?></h1>
<?cs /def ?>

<?cs def:diff_display(diff, style) ?><?cs
 if:style == 'sidebyside' ?><?cs
  each:block = diff ?><?cs
   if:block.type == 'unmod' ?><tbody class="unmod"><?cs
    each:line = block.base.lines ?><tr>
     <th class="base"><?cs var:#block.base.offset + name(line) + 1 ?></th>
     <td class="base"><span><?cs var:line ?></span>&nbsp;</td>
     <th class="chg"><?cs var:#block.changed.offset + name(line) + 1 ?></th>
     <td class="chg"><span><?cs var:block.changed.lines[name(line)] ?></span>&nbsp;</td>
    </tr><?cs /each ?>
   </tbody><?cs
   elif:block.type == 'mod' ?><tbody class="mod"><?cs
    if:len(block.base.lines) >= len(block.changed.lines) ?><?cs
     each:line = block.base.lines ?><tr>
      <th class="base"><?cs var:#block.base.offset + name(line) + 1 ?></th>
      <td class="base"><?cs var:line ?>&nbsp;</td><?cs
      if:len(block.changed.lines) >= name(line) + 1 ?><?cs
       each:changedline = block.changed.lines ?><?cs
        if:name(changedline) == name(line) ?>
         <th class="chg"><?cs var:#block.changed.offset + name(changedline) + 1 ?></th>
         <td class="chg"><?cs var:changedline ?>&nbsp;</td><?cs
        /if ?><?cs
       /each ?><?cs
      else ?>
       <th class="chg">&nbsp;</th>
       <td class="chg">&nbsp;</td><?cs
      /if ?>
     </tr><?cs /each ?><?cs
    else ?><?cs
     each:line = block.changed.lines ?><tr><?cs
      if:len(block.base.lines) >= name(line) + 1 ?><?cs
       each:baseline = block.base.lines ?><?cs
        if:name(baseline) == name(line) ?>
         <th class="base"><?cs var:#block.base.offset + name(baseline) + 1 ?></th>
         <td class="base"><?cs var:baseline ?>&nbsp;</td><?cs
        /if ?><?cs
       /each ?><?cs
      else ?>
       <th class="base">&nbsp;</th>
       <td class="base">&nbsp;</td><?cs
      /if ?>
      <th class="chg"><?cs var:#block.changed.offset + name(line) + 1 ?></th>
      <td class="chg"><?cs var:line ?>&nbsp;</td>
     </tr><?cs /each ?><?cs
    /if ?>
   </tbody><?cs
   elif:block.type == 'add' ?><tbody class="add"><?cs
    each:line = block.changed.lines ?><tr>
     <th class="base">&nbsp;</th>
     <td class="base">&nbsp;</td>
     <th class="chg"><?cs var:#block.changed.offset + name(line) + 1 ?></th>
     <td class="chg"><ins><?cs var:line ?></ins>&nbsp;</td>
    </tr><?cs /each ?><?cs
   elif:block.type == 'rem' ?><tbody class="rem"><?cs
    each:line = block.base.lines ?><tr>
     <th class="base"><?cs var:#block.base.offset + name(line) + 1 ?></th>
     <td class="base"><del><?cs var:line ?></del>&nbsp;</td>
     <th class="chg">&nbsp;</th>
     <td class="chg">&nbsp;</td>
    </tr><?cs /each ?><?cs
   /if ?>
  </tbody><?cs
  /each ?><?cs
 else ?><?cs
  each:block = diff ?>
   <?cs if:block.type == 'unmod' ?><tbody class="unmod"><?cs
    each:line = block.base.lines ?><tr>
     <th class="base"><?cs var:#block.base.offset + name(line) + #1 ?></th>
     <th class="chg"><?cs var:#block.changed.offset + name(line) + #1 ?></th>
     <td class="base"><span><?cs var:line ?></span>&nbsp;</td>
    </tr><?cs /each ?>
   </tbody>
   <?cs elif:block.type == 'mod' ?><tbody class="mod"><?cs
    each:line = block.base.lines ?><tr class="<?cs
      if:name(line) == 0 ?>first<?cs /if ?>">
     <th class="base"><?cs var:#block.base.offset + name(line) + #1 ?></th>
     <th class="chg">&nbsp;</th>
     <td class="base"><?cs var:line ?>&nbsp;</td>
    </tr><?cs /each ?><?cs
    each:line = block.changed.lines ?><tr class="<?cs
      if:name(line) + 1 == len(block.changed.lines) ?> last<?cs /if ?>">
     <th class="base">&nbsp;</th>
     <th class="chg"><?cs var:#block.changed.offset + name(line) + #1 ?></th>
     <td class="chg"><?cs var:line ?>&nbsp;</td>
    </tr><?cs /each ?>
   </tbody>
   <?cs elif:block.type == 'add' ?><tbody class="add"><?cs
    each:line = block.changed.lines ?><tr class="<?cs
      if:name(line) == 0 ?>first<?cs /if ?><?cs
      if:name(line) + 1 == len(block.changed.lines) ?> last ?><?cs /if ?>">
     <th class="base">&nbsp;</th>
     <th class="chg"><?cs var:#block.changed.offset + name(line) + #1 ?></th>
     <td class="chg"><ins><?cs var:line ?></ins>&nbsp;</td>
    </tr><?cs /each ?>
   </tbody>
   <?cs elif:block.type == 'rem' ?><tbody class="rem"><?cs
    each:line = block.base.lines ?><tr class="<?cs
      if:name(line) == 0 ?>first<?cs /if ?><?cs
      if:name(line) + 1 == len(block.base.lines) ?> last ?><?cs /if ?>">
     <th class="base"><?cs var:#block.base.offset + name(line) + 1 ?></th>
     <th class="chg">&nbsp;</th>
     <td class="base"><del><?cs var:line ?></del>&nbsp;</td>
    </tr><?cs /each ?>
   </tbody>
   <?cs /if ?><?cs
  /each ?><?cs
 /if ?><?cs
/def ?>

<?cs def:ticket_custom_props(ticket) ?><?cs
 each c=ticket.custom ?>
  <div class="field custom_<?cs var c.name ?>"><?cs
   if c.type == 'text' ?>
    <label>
     <?cs alt c.label ?><?cs var c.name ?><?cs /alt ?>:
     <input type="text" name="custom_<?cs var c.name ?>" value="<?cs var c.value ?>" />
    </label><?cs
   elif c.type == 'textarea' ?>
    <label>
     <?cs alt c.label ?><?cs var c.name ?><?cs /alt ?>:<br />
     <textarea cols="<?cs alt c.width ?>60<?cs /alt ?>" rows="<?cs
       alt c.height ?>12<?cs /alt ?>" name="custom_<?cs var c.name ?>"><?cs
       var c.value ?></textarea>
    </label><?cs
   elif c.type == 'checkbox' ?>
    <input type="hidden" name="checkbox_<?cs var c.name ?>" />
    <label>
     <input type="checkbox" name="custom_<?cs var c.name ?>" value="1"<?cs
       if c.selected ?> checked="checked"<?cs /if ?> />
     <?cs alt c.label ?><?cs var c.name ?><?cs /alt ?>
    </label><?cs
   elif c.type == 'select' ?>
    <label>
     <?cs alt c.label ?><?cs var c.name ?><?cs /alt ?>:
     <select name="custom_<?cs var c.name ?>"><?cs each v = c.option ?>
      <option<?cs if v.selected ?> selected="selected"<?cs /if ?>><?cs
        var v ?></option><?cs /each ?>
     </select>
    </label><?cs
   elif c.type == 'radio' ?>
    <fieldset class="radio">
     <legend><?cs alt c.label ?><?cs var c.name ?><?cs /alt ?>:</legend><?cs
     each v = c.option ?>
      <label><input type="radio" name="custom_<?cs var c.name ?>" value="<?cs
         var v ?>"<?cs if v.selected ?> checked="checked"<?cs /if ?> /> <?cs
         var v ?></label><?cs
     /each ?>
    </fieldset><?cs
   /if ?>
  </div><?cs
 /each ?><?cs
/def ?>
