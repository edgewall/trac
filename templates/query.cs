<?cs set:html.stylesheet = 'css/report.css' ?>
<?cs include:"header.cs" ?>
<?cs include:"macros.cs" ?>

<div id="ctxtnav" class="nav">
 <ul><?cs if:trac.acl.REPORT_VIEW ?>
  <li class="last"><a href="<?cs
    var:trac.href.report ?>">Available Reports</a></li>
 <?cs /if ?></ul>
</div>

<div id="content" class="query">
 <h1><?cs var:title ?> <span class="numrows">(<?cs alt:len(query.results) ?>No<?cs /alt ?> match<?cs
 if:len(query.results) != 1 ?>es<?cs /if ?>)</span></h1>

<form id="query" method="post" action="<?cs var:trac.href.query ?>">
 <fieldset id="filters">
  <legend>Filters</legend>
  <?cs def:checkbox_checked(constraint, option) ?><?cs
   each:value = constraint.values ?><?cs
    if:value == option ?> checked="checked"<?cs
    /if ?><?cs
   /each ?><?cs
  /def ?><?cs
  def:option_selected(constraint, option) ?><?cs
   each:value = constraint.values ?><?cs
    if:value == option ?> selected="selected"<?cs
    /if ?><?cs
   /each ?><?cs
  /def ?>
  <table><?cs each:property = ticket.properties ?><?cs
   each:constraint = query.constraints ?><?cs
    if:property.name == name(constraint) ?>
     <tbody><tr class="<?cs var:property.name ?>">
      <th scope="row"><label><?cs var:property.label ?></label></th><?cs
      if:property.type != "radio" ?>
       <td class="mode">
        <select name="<?cs var:property.name ?>_mode"><?cs
         each:mode = query.modes[property.type] ?>
          <option value="<?cs var:mode.value ?>"<?cs
           if:mode.value == constraint.mode ?> selected="selected"<?cs
           /if ?>><?cs var:mode.name ?></option><?cs
         /each ?>
        </select>
       </td><?cs
      /if ?>
      <td class="filter"<?cs if:property.type == "radio" ?> colspan="2"<?cs /if ?>><?cs
       if:property.type == "select" ?><?cs
        each:value = constraint.values ?>
         <select name="<?cs var:name(constraint) ?>"><option></option><?cs
         each:option = property.options ?>
          <option<?cs if:option == value ?> selected="selected"<?cs /if ?>><?cs
            var:option ?></option><?cs
         /each ?></select><?cs
         if:name(value) != len(constraint.values) - 1 ?>
          </td>
          <td class="actions"><input type="submit" name="rm_filter_<?cs
             var:property.name ?>_<?cs var:name(value) ?>" value="-" /></td>
         </tr><tr class="<?cs var:property.name ?>">
          <th colspan="2"><label>or</label></th>
          <td class="filter"><?cs
         /if ?><?cs
        /each ?><?cs
       elif:property.type == "radio" ?><?cs
        each:option = property.options ?>
         <input type="checkbox" id="<?cs var:property.name ?>_<?cs
           var:option ?>" name="<?cs var:property.name ?>" value="<?cs
           var:option ?>"<?cs call:checkbox_checked(constraint, option) ?> />
         <label for="<?cs var:property.name ?>_<?cs var:option ?>"><?cs
           alt:option ?>none<?cs /alt ?></label><?cs
        /each ?><?cs
       elif:property.type == "text" ?><?cs
        each:value = constraint.values ?>
        <input type="text" name="<?cs var:property.name ?>" value="<?cs
          var:value ?>" size="42" /><?cs
         if:name(value) != len(constraint.values) - 1 ?>
          </td>
          <td class="actions"><input type="submit" name="rm_filter_<?cs
             var:property.name ?>_<?cs var:name(value) ?>" value="-" /></td>
         </tr><tr class="<?cs var:property.name ?>">
          <th colspan="2"><label>or</label></th>
          <td class="filter"><?cs
         /if ?><?cs
        /each ?><?cs
       /if ?>
      </td>
      <td class="actions"><input type="submit" name="rm_filter_<?cs
         var:property.name ?><?cs
         if:property.type != "radio" ?>_<?cs
          var:len(constraint.values) - 1 ?><?cs
         /if ?>" value="-" /></td>
     </tr></tbody><?cs /if ?><?cs
    /each ?><?cs
   /each ?>
   <tr>
    <td class="actions" colspan="4" style="text-align: right">
     <label for="add_filter">Add filter</label>&nbsp;
     <select name="add_filter" id="add_filter">
      <option></option><?cs
      each:property = ticket.properties ?>
       <option value="<?cs var:property.name ?>"<?cs
         if:property.type == "radio" ?><?cs
          if:len(query.constraints[property.name]) != 0 ?> disabled="disabled"<?cs
          /if ?><?cs
         /if ?>><?cs var:property.label ?></option><?cs
      /each ?>	
     </select>
     <input type="submit" name="add" value="+" />
    </td>
   </tr>
  </table>
 </fieldset>
 <p class="option">
  <label for="group">Group results by</label>
  <select name="group" id="group">
   <option></option><?cs
   each:property = ticket.properties ?><?cs
    if:property.type == 'select' || property.type == 'radio' ||
       property.name == 'owner' ?>
     <option value="<?cs var:property.name ?>"<?cs
       if:property.name == query.group ?> selected="selected"<?cs /if ?>><?cs
       var:property.label ?></option><?cs
    /if ?><?cs
   /each ?>
  </select>
  <input type="checkbox" name="groupdesc" id="groupdesc"<?cs
    if:query.groupdesc ?> checked="checked"<?cs /if ?> />
  <label for="groupdesc">descending</label>
  <script type="text/javascript">
    var group = document.getElementById("group");
    var updateGroupDesc = function() {
      enableControl('groupdesc', group.selectedIndex > 0);
    }
    addEvent(window, 'load', updateGroupDesc);
    addEvent(group, 'change', updateGroupDesc);
  </script>
 </p>
 <p class="option">
  <input type="checkbox" name="verbose" id="verbose"<?cs
    if:query.verbose ?> checked="checked"<?cs /if ?> />
  <label for="verbose">Show full description under each result</label>
 </p>
 <div class="buttons">
  <input type="hidden" name="order" value="<?cs var:query.order ?>" />
  <?cs if:query.desc ?><input type="hidden" name="desc" value="1" /><?cs /if ?>
  <input type="submit" name="update" value="Update" />
 </div>
 <hr />
</form>
<script type="text/javascript" src="<?cs
  var:htdocs_location ?>js/query.js"></script>
<script type="text/javascript">
  initializeFilters();
</script>

<?cs def:thead() ?>
 <thead><tr><?cs each:header = query.headers ?><?cs
  if:name(header) == 0 ?><th class="ticket<?cs
   if:header.order ?> <?cs var:header.order ?><?cs /if ?>">
   <a href="<?cs var:header.href ?>" title="Sort by ID (<?cs
     if:header.order == 'asc' ?>descending<?cs
     else ?>ascending<?cs /if ?>)">Ticket</a>
   </th><?cs
  else ?>
   <th<?cs if:header.order ?> class="<?cs var:header.order ?>"<?cs /if ?>>
    <a href="<?cs var:header.href ?>" title="Sort by <?cs
      var:header.name ?> (<?cs if:header.order == 'asc' ?>descending<?cs
      else ?>ascending<?cs /if ?>)"><?cs
       each:property = ticket.properties ?><?cs
        if:property.name == header.name ?><?cs
         var:property.label ?><?cs
        /if ?><?cs
       /each ?></a>
   </th><?cs
  /if ?>
 <?cs /each ?></tr></thead>
<?cs /def ?>

<?cs if:len(query.results) ?><?cs
 if:!query.group ?>
  <table class="listing tickets">
  <?cs call:thead() ?><tbody><?cs
 /if ?><?cs
 each:result = query.results ?><?cs
  if:result[query.group] != prev_group ?>
   <?cs if:prev_group ?></tbody></table><?cs /if ?>
   <h2><?cs
    each:property = ticket.properties ?><?cs
     if:property.name == query.group ?><?cs
      var:property.label ?><?cs
     /if ?><?cs
    /each ?>: <?cs var:result[query.group] ?></h2>
   <table class="listing tickets">
   <?cs call:thead() ?><tbody><?cs
  /if ?>
  <tr class="<?cs
   if:name(result) % 2 ?>odd<?cs else ?>even<?cs /if ?> <?cs
   var:result.priority ?>"><?cs
  each:header = query.headers ?><?cs
   if:name(header) == 0 ?>
    <td class="ticket"><a href="<?cs var:result.href ?>" title="View ticket"><?cs
      var:result.id ?></a></td><?cs
   else ?>
    <td><?cs if:header.name == 'summary' ?>
     <a href="<?cs var:result.href ?>" title="View ticket"><?cs
       var:result[header.name] ?></a><?cs
    else ?>
     <?cs var:result[header.name] ?><?cs
    /if ?>
    </td><?cs
   /if ?><?cs
  /each ?>
  <?cs if:query.verbose ?>
   </tr><tr class="fullrow"><td colspan="<?cs var:len(query.headers) ?>">
    <p class="meta">Reported by <strong><?cs var:result.reporter ?></strong>,
    <?cs var:result.created ?><?cs if:result.description ?>:<?cs /if ?></p>
    <?cs if:result.description ?><p><?cs var:result.description ?></p><?cs /if ?>
   </td>
  <?cs /if ?><?cs set:prev_group = result[query.group] ?>
 </tr><?cs /each ?>
</tbody></table><?cs
/if ?>

<div id="help">
 <strong>Note:</strong> See <a href="<?cs var:$trac.href.wiki ?>/TracQuery">TracQuery</a> 
 for help on using queries.
</div>

<script type="text/javascript" defer="defer"><?cs set:idx = 0 ?>
 var properties={<?cs each:property = ticket.properties ?><?cs
  var:property.name ?>:{type:"<?cs var:property.type ?>",label:"<?cs
  var:property.label ?>",options:[<?cs
   each:option = property.options ?>"<?cs var:option ?>"<?cs
    if:name(option) < len(property.options) -1 ?>,<?cs /if ?><?cs
   /each ?>]}<?cs
  set:idx = idx + 1 ?><?cs if:idx < len(ticket.properties) ?>,<?cs /if ?><?cs
 /each ?>};<?cs set:idx = 0 ?>
 var modes = {<?cs each:type = query.modes ?><?cs var:name(type) ?>:[<?cs
  each:mode = type ?>{text:"<?cs var:mode.name ?>",value:"<?cs var:mode.value ?>"}<?cs
   if:name(mode) < len(type) -1 ?>,<?cs /if ?><?cs
  /each ?>]<?cs
  set:idx = idx + 1 ?><?cs if:idx < len(query.modes) ?>,<?cs /if ?><?cs
 /each ?>};
</script>

</div>
<?cs include:"footer.cs" ?>
