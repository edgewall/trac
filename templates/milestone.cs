<?cs include "header.cs"?>
<?cs include "macros.cs"?>

<ul class="subheader-links">
 <?cs if:milestone.href.edit ?><li class="first"><a href="<?cs
   var:milestone.href.edit ?>">Edit Milestone Info</a></li><?cs /if ?>
 <?cs if:milestone.href.delete ?><li class="last"><a href="<?cs
   var:milestone.href.delete ?>">Delete Milestone</a></li><?cs /if ?>
</ul>

<div id="main" class="milestone">
 <?cs if:milestone.mode == "new" ?>
 <h1>New Milestone</h1>
 <?cs elif:milestone.mode == "edit" ?>
 <h1>Edit Milestone</h1>
 <?cs else ?>
 <h1>Milestone <em><?cs var:milestone.name ?></em></h1>
 <?cs /if ?>

 <?cs if:milestone.mode == "edit" || milestone.mode == "new" ?>
  <script type="text/javascript">
    addEvent(window, 'load', function() {
      document.getElementById('name').focus() }
    ); 
  </script>
  <form action="<?cs var:cgi_location ?>" method="post">
   <input type="hidden" name="mode" value="milestone" />   <input type="hidden" name="id" value="<?cs var:milestone.name ?>" />   <input type="hidden" name="action" value="commit" />   <fieldset>
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
   </fieldset>
   <div class="buttons">
    <input type="submit" name="cancel" value="Cancel" />
    <input type="reset" type="Reset" value="Reset" />
    <input type="submit" name="save" value="Submit Changes" />
   </div>
  </form>
 <?cs else ?>
  <em class="date"><?cs if:milestone.date ?>
   <?cs var:milestone.date ?><?cs else ?>No date set<?cs /if ?>
  </em>
  <div class="description"><?cs var:milestone.description ?></div>
 <?cs /if ?>

 <?cs with:stats = milestone.stats ?>
  <table summary="Shows the milestone completion status grouped by component">
   <caption>Status By Component</caption>
   <thead><tr>
    <th class="name" scope="col">Component</th>
    <th class="tickets" scope="col">Active Tickets</th>
    <th class="progress" scope="col">Percent Complete</th>
   </tr></thead>
   <tbody>
    <?cs each:component = milestone.stats.components ?>
     <tr class="<?cs if:name(component) % 2 ?>odd<?cs else ?>even<?cs /if ?>">
      <th class="name" scope="row"><?cs var:component.name ?></th>
      <td class="tickets">
       <?cs var:component.active_tickets ?> /
       <?cs var:component.closed_tickets ?>
      </td>
      <td class="progress">
       <div style="width: 80%">
        <div class="progress" style="width: <?cs
          var:#component.percent_total ?>%"><div style="width: <?cs
          var:#component.percent_complete ?>%"></div>
        </div>
       </div>
       <p><?cs var:#component.percent_complete ?>%</p>
      </td>
     </tr>
    <?cs /each ?>
   </tbody>
   <tfoot><tr>
    <th class="name" scope="row">Total</th>
    <td class="tickets">
     <?cs var:stats.active_tickets ?> /
     <?cs var:stats.closed_tickets ?>
    </td>
    <td class="progress">
     <div style="width: 80%">
      <div class="progress" style="width: 100%">
       <div style="width: <?cs var:#stats.percent_complete ?>%"></div>
      </div>
     </div>
     <p class="percentage"><?cs var:#stats.percent_complete ?>%</p>
    </td>
   </tr></tfoot>
  </table>
 <?cs /with ?>

</div>
<?cs include:"footer.cs"?>
