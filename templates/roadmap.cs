<?cs include "header.cs"?>
<?cs include "macros.cs"?>
<div id="main" class="roadmap">
 <h1>Roadmap</h1>

 <ul><?cs each:milestone = roadmap.milestones ?>
  <li>
   <h2>Milestone: <a href="<?cs var:milestone.href ?>"><?cs
     var:milestone.name ?></a></h2>
   <em class="date"><?cs if:milestone.date ?>
    <?cs var:milestone.date ?><?cs else ?>No date set<?cs /if ?>
   </em>
   <?cs with:stats = milestone.stats ?>
    <div class="progress">
     <div style="width: <?cs var:#stats.percent_complete ?>%"></div>
    </div>
    <p><?cs var:#stats.percent_complete ?>%</p>
    <dl>
     <dt>Active tickets:</dt>
     <dd><?cs var:stats.active_tickets ?></dd>
     <dt>Resolved tickets:</dt>
     <dd><?cs var:stats.closed_tickets ?></dd>
    </dl>
   <?cs /with ?>
   <p class="description"><?cs var:milestone.description ?></p>
  </li>
 <?cs /each ?></ul>

</div>
<?cs include:"footer.cs"?>
