<?cs include "header.cs"?>

<div class="nav">
 <h2>Timeline Navigation</h2>
 <ul class="subheader-links">
   <li class="last"><a href="?daysback=90&amp;max=50&amp;format=rss">RSS Feed</a></li>
 </ul>
</div>

<div id="main" class="timeline">
 <h1>Timeline</h1>

 <form id="prefs" action="<?cs var:trac.href.timeline ?>">
  <label for="from">View changes from</label>
  <input type="text" size="10" id="from" name="from"
      value="<?cs var:timeline.from ?>" /> and <input type="text" size="3"
      id="daysback" name="daysback"  value="<?cs var:timeline.daysback ?>" />
  <label for="daysback">days back</label>.
  <fieldset>
   <div class="field">
    <input type="checkbox" id="ticket" name="ticket" <?cs
      if:timeline.ticket ?>checked="checked"<?cs /if ?> />
    <label for="ticket">Ticket changes</label>
   </div>
   <div class="field">
    <input type="checkbox" id="changeset" name="changeset" <?cs
      if:timeline.changeset ?>checked="checked"<?cs /if ?> />
    <label for="changeset">Repository checkins</label>
   </div>
   <div class="field">
    <input type="checkbox" id="wiki" name="wiki" <?cs
      if:timeline.wiki ?>checked="checked"<?cs /if ?> />
    <label for="wiki">Wiki changes</label>
   </div>
   <div class="field">
    <input type="checkbox" id="milestone" name="milestone" <?cs
      if:timeline.milestone ?>checked="checked"<?cs /if ?> />
    <label for="milestone">Milestones</label>
   </div>
  </fieldset>
  <div class="buttons">
   <input type="submit" value="Update" />
  </div>
 </form>

<?cs def:day_separator(date) ?>
 <?cs if: $date != $current_date ?>
  <?cs if: $current_date ?></dl><?cs /if ?>
  <?cs set: $current_date = $date ?>
  <h2><?cs var:date ?>:</h2>
  <dl>
 <?cs /if ?>
<?cs /def ?>

<?cs def:tlitem(url, type, msg, descr) ?>
 <dt class="<?cs var:type ?>">
  <a href="<?cs var:url ?>"><span class="time"><?cs
    var:item.time ?> :</span> <?cs var:msg ?></a>
 </dt>
 <?cs if:descr ?><dd><?cs var:descr ?></dd><?cs /if ?>
<?cs /def ?>

<?cs each:item = timeline.items ?>
 <?cs call:day_separator(item.date) ?>
 <?cs if:item.type == #1 ?><!-- Changeset -->
  <?cs call:tlitem(item.href, 'changeset',
    'Changeset <em>['+$item.idata+']</em> by '+$item.author, item.message) ?>
 <?cs elif:item.type == #2 ?><!-- New ticket -->
  <?cs call:tlitem(item.href, 'newticket',
    'Ticket <em>#'+$item.idata+'</em> created by '+$item.author, item.message) ?>
 <?cs elif:item.type == #3 ?><!-- Closed ticket -->
  <?cs call:tlitem(item.href, 'closedticket',
    'Ticket <em>#'+$item.idata+'</em> resolved by '+$item.author, '') ?>
 <?cs elif:item.type == #4 ?><!-- Reopened ticket -->
  <?cs call:tlitem(item.href, 'newticket',
    'Ticket <em>#'+$item.idata+'</em> reopened by '+$item.author, '') ?>
 <?cs elif:item.type == #5 ?><!-- Wiki change -->
  <?cs call:tlitem(item.href, 'wiki',
    '<em>'+$item.tdata+'</em> edited by '+$item.author, item.message) ?>
 <?cs elif:item.type == #6 ?><!-- milestone -->
  <?cs call:tlitem(item.href, 'milestone',
    '<em>Milestone '+$item.message+'</em> reached', '') ?>
 <?cs /if ?>
<?cs /each ?>

<div id="help">
 <hr />
 <strong>Note:</strong> See <a href="<?cs var:$trac.href.wiki ?>/TracTimeline">TracTimeline</a> 
 for information about the timeline view.
</div>

 <div id="main-footer">
  Download in other formats: <br />
  <a class="noline" href="?daysback=90&amp;max=50&amp;format=rss"><img src="<?cs var:htdocs_location
?>xml.png" alt="RSS Feed" style="vertical-align: bottom"/></a>&nbsp;
  <a href="?daysback=90&amp;max=50&amp;format=rss">(RSS 2.0)</a>
  <br />
 </div>

</div>
<?cs include:"footer.cs"?>
