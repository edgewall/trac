<?cs include "header.cs"?>
<?cs include "macros.cs"?>
<div id="main" class="roadmap">
 <h1>Roadmap</h1>

 <ul><?cs each:milestone = roadmap.milestones ?>
  <li>
   <h2><a href="<?cs var:milestone.href ?>">Milestone: <em><?cs
     var:milestone.name ?></em></a></h2>
   <p class="date"><?cs if:milestone.date ?>
    <?cs var:milestone.date ?><?cs else ?>No date set<?cs /if ?>
   </p>
   <?cs with:stats = milestone.stats ?>
    <?cs if:#stats.total_tickets > #0 ?>
     <div class="progress">
      <div style="width: <?cs var:#stats.percent_complete ?>%"></div>
     </div>
     <p class="percentage"><?cs var:#stats.percent_complete ?>%</p>
     <dl>
      <dt>Active tickets:</dt>
      <dd><?cs var:stats.active_tickets ?></dd>
      <dt>Resolved tickets:</dt>
      <dd><?cs var:stats.closed_tickets ?></dd>
     </dl>
    <?cs /if ?>
   <?cs /with ?>
   <p class="description"><?cs var:milestone.description ?></p>
  </li>
 <?cs /each ?></ul>

</div>
<?cs include:"footer.cs"?>
