<?cs include:"header.cs"?>
<?cs include:"macros.cs"?>

<div id="ctxtnav" class="nav"></div>

<div id="content" class="milestone">
 <?cs if:milestone.mode == "new" ?>
 <h1>New Milestone</h1>
 <?cs elif:milestone.mode == "edit" ?>
 <h1>Edit Milestone <?cs var:milestone.name ?></h1>
 <?cs elif:milestone.mode == "delete" ?>
 <h1>Delete Milestone <?cs var:milestone.name ?></h1>
 <?cs else ?>
 <h1>Milestone <?cs var:milestone.name ?></h1>
 <?cs /if ?>

 <?cs if:milestone.mode == "edit" || milestone.mode == "new" ?>
  <script type="text/javascript">
    addEvent(window, 'load', function() {
      document.getElementById('name').focus();
    });
  </script>
  <form id="edit" action="<?cs var:milestone.href ?>" method="post">
   <input type="hidden" name="id" value="<?cs var:milestone.name ?>" />
   <input type="hidden" name="action" value="edit" />
   <div class="field">
    <label>Name of the milestone:<br />
    <input type="text" id="name" name="name" size="32" value="<?cs
      var:milestone.name ?>" /></label>
   </div>
   <fieldset>
    <legend>Schedule</legend>
    <label>Due:<br />
     <input type="text" id="duedate" name="duedate" size="<?cs
       var:len(milestone.date_hint) ?>" value="<?cs
       var:milestone.due_date ?>" title="Format: <?cs var:milestone.date_hint ?>" />
     <em>Format: <?cs var:milestone.date_hint ?></em>
    </label>
    <div class="field">
     <label>
      <input type="checkbox" id="completed" name="completed"<?cs
        if:milestone.completed ?> checked="checked"<?cs /if ?> />
      Completed:<br />
     </label>
     <label>
      <input type="text" id="completeddate" name="completeddate" size="<?cs
        var:len(milestone.date_hint) ?>" value="<?cs
        alt:milestone.completed_date ?><?cs
         var:milestone.datetime_now ?><?cs
        /alt ?>" title="Format: <?cs
        var:milestone.datetime_hint ?>" />
      <em>Format: <?cs var:milestone.datetime_hint ?></em>
     </label><?cs
     if:len(milestones) ?>
     <br/>
     <input type="checkbox" id="retarget" name="retarget" checked="checked"
            onclick="enableControl('target', this.checked)"/>
     <label>
      Retarget associated open tickets to milestone
      <select id="target" name="target">
       <option value="">None</option><?cs
       each:name = milestones ?>
       <option><?cs var:name ?></option><?cs
       /each ?>
      </select>
     </label><?cs
     /if ?>
     <script type="text/javascript">
       var completed = document.getElementById("completed");
       var retarget = document.getElementById("retarget");
       var enableCompletedDate = function() {
         enableControl("completeddate", completed.checked);
         enableControl("retarget", completed.checked);
         enableControl("target", completed.checked && retarget.checked);
       };
       addEvent(window, "load", enableCompletedDate);
       addEvent(completed, "click", enableCompletedDate);
     </script>
    </div>
   </fieldset>
   <div class="field">
    <fieldset class="iefix">
     <label for="description">Description (you may use <a tabindex="42" href="<?cs
       var:trac.href.wiki ?>/WikiFormatting">WikiFormatting</a> here):</label>
     <p><textarea id="description" name="description" class="wikitext" rows="10" cols="78">
<?cs var:milestone.description_source ?></textarea></p>
    </fieldset>
   </div>
   <div class="buttons">
    <?cs if:milestone.mode == "new"
     ?><input type="submit" value="Add milestone" /><?cs
    else
     ?><input type="submit" value="Submit changes" /><?cs
    /if ?>
    <input type="submit" name="cancel" value="Cancel" />
   </div>
   <script type="text/javascript" src="<?cs
     var:htdocs_location ?>js/wikitoolbar.js"></script>
  </form>
 <?cs elif:milestone.mode == "delete" ?>
  <form action="<?cs var:milestone.href ?>" method="post">
   <input type="hidden" name="id" value="<?cs var:milestone.name ?>" />
   <input type="hidden" name="action" value="delete" />
   <p><strong>Are you sure you want to delete this milestone?</strong></p>
   <input type="checkbox" id="retarget" name="retarget" checked="checked"
       onclick="enableControl('target', this.checked)"/>
   <label for="target">Retarget associated tickets to milestone</label>
   <select name="target" id="target">
    <option value="">None</option><?cs
     each:other = milestones ?><?cs if:other != milestone.name ?>
      <option><?cs var:other ?></option><?cs 
     /if ?><?cs /each ?>
   </select>
   <div class="buttons">
    <input type="submit" name="cancel" value="Cancel" />
    <input type="submit" value="Delete milestone" />
   </div>
  </form>
 <?cs else ?>
 <?cs if:milestone.mode == "view" ?>
  <div class="info">
   <p class="date"><?cs
    if:milestone.completed_date ?>
     Completed <?cs var:milestone.completed_delta ?> ago (<?cs var:milestone.completed_date ?>)<?cs
    elif:milestone.due_date ?><?cs
     if:milestone.late ?>
      <strong><?cs var:milestone.due_delta ?> late</strong><?cs
     else ?>
      Due in <?cs var:milestone.due_delta ?><?cs
     /if ?> (<?cs var:milestone.due_date ?>)<?cs
    else ?>
     No date set<?cs
    /if ?>
   </p><?cs
   with:stats = milestone.stats ?><?cs
    if:#stats.total_tickets > #0 ?>
     <table class="progress">
      <tr>
      <td class="closed" style="width: <?cs
        var:#stats.percent_closed ?>%">
        <a href="<?cs
        var:milestone.queries.closed_tickets ?>" title="<?cs
        var:#stats.closed_tickets ?> of <?cs
        var:#stats.total_tickets ?> ticket<?cs
        if:#stats.total_tickets != #1 ?>s<?cs /if ?> closed"></a></td>
      <td class="open" style="width: <?cs
        var:#stats.percent_active ?>%">
        <a href="<?cs
        var:milestone.queries.active_tickets ?>" title="<?cs
        var:#stats.active_tickets ?> of <?cs
        var:#stats.total_tickets ?> ticket<?cs
        if:#stats.total_tickets != #1 ?>s<?cs /if ?> active"></a>
      </tr>
     </table>
     <p class="percent"><?cs var:#stats.percent_closed ?>%</p>
     <dl>
      <dt>Closed tickets:</dt>
      <dd><a href="<?cs var:milestone.queries.closed_tickets ?>"><?cs
        var:stats.closed_tickets ?></a></dd>
      <dt>Active tickets:</dt>
      <dd><a href="<?cs var:milestone.queries.active_tickets ?>"><?cs
        var:stats.active_tickets ?></a></dd>
     </dl><?cs
    /if ?><?cs
   /with ?>
  </div>
  <form id="stats" action="" method="get">
   <fieldset>
    <legend>
     <label for="by">Ticket status by</label>
     <select id="by" name="by" onchange="this.form.submit()"><?cs
     each:group = milestone.stats.available_groups ?>
      <option value="<?cs var:group.name ?>" <?cs
        if:milestone.stats.grouped_by == group.name ?> selected="selected"<?cs
        /if ?>><?cs var:group.label ?></option><?cs
     /each ?></select>
     <noscript><input type="submit" value="Update" /></noscript>
    </legend>
    <table summary="Shows the milestone completion status grouped by <?cs
      var:milestone.stats.grouped_by ?>"><?cs
     each:group = milestone.stats.groups ?>
      <tr>
       <th scope="row"><a href="<?cs
         var:group.queries.all_tickets ?>"><?cs var:group.name ?></a></th>
       <td style="white-space: nowrap"><?cs if:#group.total_tickets ?>
        <table class="progress" style="width: <?cs
          var:#group.percent_total * #80 / #milestone.stats.max_percent_total ?>%">
         <tr>
          <td class="closed" style="width: <?cs
            var:#group.percent_closed ?>%"><a href="<?cs
            var:group.queries.closed_tickets ?>" title="<?cs
           var:group.closed_tickets ?> of <?cs
           var:group.total_tickets ?> ticket<?cs
           if:group.total_tickets != #1 ?>s<?cs /if ?> closed"></a>
          </td>
          <td class="open" style="width: <?cs
            var:#group.percent_active ?>%"><a href="<?cs
            var:group.queries.active_tickets ?>" title="<?cs
           var:group.active_tickets ?> of <?cs
           var:group.total_tickets ?> ticket<?cs
           if:group.total_tickets != 1 ?>s<?cs /if ?> active"></a>
          </td>
         </tr>
        </table>
        <p class="percent"><?cs var:group.closed_tickets ?>/<?cs
         var:group.total_tickets ?></p>
       <?cs /if ?></td>
      </tr><?cs
     /each ?>
    </table><?cs /if ?>
   </fieldset>
  </form>
  <div class="description"><?cs var:milestone.description ?></div><?cs
  if:trac.acl.MILESTONE_MODIFY || trac.acl.MILESTONE_DELETE ?>
   <div class="buttons"><?cs
    if:trac.acl.MILESTONE_MODIFY ?>
     <form method="get" action=""><div>
      <input type="hidden" name="action" value="edit" /><?cs
      if:milestone.id_param ?>
       <input type="hidden" name="id" value="<?cs var:milestone.name ?>" /><?cs
      /if ?>
      <input type="submit" value="Edit milestone info" accesskey="e" />
     </div></form><?cs
    /if ?><?cs
    if:trac.acl.MILESTONE_DELETE ?>
     <form method="get" action=""><div>
      <input type="hidden" name="action" value="delete" /><?cs
      if:milestone.id_param ?>
       <input type="hidden" name="id" value="<?cs var:milestone.name ?>" /><?cs
      /if ?>
      <input type="submit" value="Delete milestone" />
     </div></form><?cs
    /if ?>
   </div><?cs
  /if ?><?cs
 /if ?>

 <div id="help">
  <strong>Note:</strong> See <a href="<?cs
    var:trac.href.wiki ?>/TracRoadmap">TracRoadmap</a> for help on using the roadmap.
 </div>

</div>
<?cs include:"footer.cs"?>
