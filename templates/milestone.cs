<?cs include "header.cs"?>
<?cs include "macros.cs"?>
<div id="main" class="milestone">
 <h1>Milestone <em><?cs var:milestone.name ?></em></h1>

 <em class="date"><?cs if:milestone.date ?>
  <?cs var:milestone.date ?><?cs else ?>No date set<?cs /if ?>
 </em>
 <div class="description"><?cs var:milestone.description ?></div>

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
