<?cs include "header.cs"?>
<?cs include "macros.cs"?>

<ul class="subheader-links">
 <?cs if:roadmap.href.newmilestone ?><li class="last"><a href="<?cs
   var:roadmap.href.newmilestone ?>">Add New Milestone</a></li><?cs /if ?>
</ul>

<div id="main" class="roadmap">
 <h1>Roadmap</h1>

 <ul class="milestones"><?cs each:milestone = roadmap.milestones ?>
  <li class="milestone">
   <div class="info">
    <h2><a href="<?cs var:milestone.href ?>">Milestone: <em><?cs
      var:milestone.name ?><?cs if:milestone.title ?> &#8216;<?cs
      var:milestone.title ?>&#8217;<?cs /if ?></em></a></h2>
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
   </div>
   <div class="description"><?cs var:milestone.description ?></div>
  </li>
 <?cs /each ?></ul>

</div>
<?cs include:"footer.cs"?>
