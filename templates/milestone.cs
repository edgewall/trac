<?cs set:html.stylesheet = 'css/roadmap.css' ?>
<?cs include "header.cs"?>
<?cs include "macros.cs"?>

<div id="ctxtnav" class="nav">
 <ul>
  <?cs if:milestone.href.edit ?><li class="first"><a href="<?cs
    var:milestone.href.edit ?>">Edit Milestone Info</a></li><?cs /if ?>
  <?cs if:milestone.href.delete ?><li class="last"><a href="<?cs
    var:milestone.href.delete ?>">Delete Milestone</a></li><?cs /if ?>
 </ul>
</div>

<div id="content" class="milestone">
 <?cs if:milestone.mode == "new" ?>
 <h1>New Milestone</h1>
 <?cs elif:milestone.mode == "edit" ?>
 <h1>Edit Milestone</h1>
 <?cs elif:milestone.mode == "delete" ?>
 <h1>Delete Milestone <?cs var:milestone.name ?></h1>
 <?cs else ?>
 <h1>Milestone <?cs var:milestone.name ?></h1>
 <?cs /if ?>

 <?cs if:milestone.mode == "edit" || milestone.mode == "new" ?>
  <script type="text/javascript">
    addEvent(window, 'load', function() {
      document.getElementById('name').focus() }
    );
  </script>
  <form action="<?cs var:cgi_location ?>" method="post">
   <input type="hidden" name="mode" value="milestone" />
   <input type="hidden" name="id" value="<?cs var:milestone.name ?>" />
   <input type="hidden" name="action" value="commit_changes" />
   <fieldset>
    <legend>Properties</legend>
    <div class="field">
     <label for="name">Name:</label>
     <input type="text" id="name" name="name" value="<?cs
       var:milestone.name ?>" />
    </div>
    <div class="field">
     <label for="date">Date:</label>
     <input type="text" id="date" name="date" size="8" value="<?cs
       var:milestone.date ?>" /> <em>Format: MM/DD/YY</em>
    </div>
    <div class="field">
     <input type="checkbox" id="updatetickets" name="updatetickets"
       checked="checked" />
     <label for="updatetickets">Update all tickets associated with this
     milestone when the name is changed</label>
    </div>
   </fieldset>
   <fieldset>
    <legend>Description</legend>
    <div class="field">
     <label for="descr">You may use <a tabindex="42"
       href="<?cs var:trac.href.wiki ?>/WikiFormatting">WikiFormatting</a>
       here:</label>
     <textarea id="descr" name="descr" rows="15" cols="80"
         style="width: 97%"><?cs var:milestone.descr_source ?></textarea>
     <?cs call:wiki_toolbar('descr') ?>
    </div>
   </fieldset>
   <div class="buttons">
    <input type="submit" name="cancel" value="Cancel" />
    <input type="reset" type="Reset" value="Reset" />
    <input type="submit" name="save" value="Submit Changes" />
   </div>
  </form>
 <?cs elif:milestone.mode == "delete" ?>
  <form action="<?cs var:cgi_location ?>" method="post">
   <input type="hidden" name="mode" value="milestone" />   <input type="hidden" name="id" value="<?cs var:milestone.name ?>" />   <input type="hidden" name="action" value="confirm_delete" />
   <p><strong>Are you sure you want to delete this milestone?</strong></p>
   <input type="checkbox" id="resettickets" name="resettickets"
     checked="checked"/>
   <label for="resettickets">Reset the milestone field of all tickets
   associated with this milestone?</label>
   <div class="buttons">
    <input type="submit" name="cancel" value="Cancel" />
    <input type="submit" name="delete" value="Delete Milestone" />
   </div>
  </form>
 <?cs else ?>
  <em class="date"><?cs if:milestone.date ?>
   <?cs var:milestone.date ?><?cs else ?>No date set<?cs /if ?>
  </em>
  <div class="descr"><?cs var:milestone.descr ?></div>
 <?cs /if ?>

 <?cs with:stats = milestone.stats ?>
  <table class="listing" id="stats"
    summary="Shows the milestone completion status grouped by component">
   <caption>Status By Component</caption>
   <thead><tr>
    <th>&nbsp;</th>
    <th class="tickets" scope="col" colspan="2">Tickets</th>
    <th>&nbsp;</th>
   </tr><tr>
    <th class="name" scope="col">Component</th>
    <th class="open" scope="col">Active</th>
    <th class="closed" scope="col">Resolved</th>
    <th class="progress" scope="col">Percent Resolved</th>
   </tr></thead>
   <tbody>
    <?cs each:component = milestone.stats.components ?>
     <tr class="<?cs if:name(component) % 2 ?>odd<?cs else ?>even<?cs /if ?>">
      <th class="name" scope="row"><?cs var:component.name ?></th>
      <td class="open tickets"><?cs var:component.active_tickets ?></td>
      <td class="closed tickets"><?cs var:component.closed_tickets ?></td>
      <td class="progress">
       <?cs if:#component.total_tickets ?>
        <div style="width: 80%">
         <div class="progress" style="width: <?cs
           var:#component.percent_total ?>%"><div style="width: <?cs
           var:#component.percent_complete ?>%"></div>
         </div>
        </div>
        <p><?cs var:#component.percent_complete ?>%</p>
       <?cs /if ?>
      </td>
     </tr>
    <?cs /each ?>
   </tbody>
   <tfoot><tr>
    <th class="name" scope="row">Total</th>
    <td class="open tickets"><?cs var:stats.active_tickets ?></td>
    <td class="closed tickets"><?cs var:stats.closed_tickets ?></td>
    <td class="progress">
     <?cs if:#stats.total_tickets ?>
      <div style="width: 80%">
       <div class="progress" style="width: 100%">
        <div style="width: <?cs var:#stats.percent_complete ?>%"></div>
       </div>
      </div>
      <p class="percentage"><?cs var:#stats.percent_complete ?>%</p>
     <?cs /if ?>
    </td>
   </tr></tfoot>
  </table>
 <?cs /with ?>

</div>
<?cs include:"footer.cs"?>
