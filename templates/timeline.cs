<?cs include "header.cs"?>
<div id="page-content">
<div id="subheader-links">
  <a href="?daysback=90&amp;max=50&amp;format=rss">RSS Feed </a>
</div>

<div id="main">
  <div id="main-content">

<h1 id="timeline-hdr">Timeline</h1>

<form action="<?cs var:trac.href.timeline ?>">
  <div id="timeline-prefs">
    <label for="from">View changes from</label>
    <input size="10" id="from" name="from" value="<?cs var:timeline.from ?>" />
    and <input size="3" id="daysback" name="daysback" 
           value="<?cs var:timeline.daysback ?>" />
    <label for="daysback">days back</label>.
  <div id="timeline-prefs-checks">
    <input type="checkbox" id="ticket" name="ticket" 
           <?cs if:timeline.ticket ?>checked="checked"<?cs /if ?> />
    <label for="ticket">Ticket changes</label><br />
    <input type="checkbox" id="changeset" name="changeset" 
           <?cs if:timeline.changeset ?>checked="checked"<?cs /if ?> />
    <label for="changeset">Repository checkins</label><br />
    <input type="checkbox" id="wiki" name="wiki"
           <?cs if:timeline.wiki ?>checked="checked"<?cs /if ?> />
   <label for="wiki">Wiki changes</label>
  </div>
  <div id="timeline-prefs-btns">
    <input type="submit" value="Update" /> 
  </div>
  </div>
</form>

<?cs def:day_separator(date) ?>
  <?cs if: $date != $current_date ?>
    <?cs set: $current_date = $date ?>
      <h2 class="timeline-daysep"><?cs var:date ?>:</h2>
  <?cs /if ?>
<?cs /def ?>

<?cs def:tlitem(url,icon,msg,descr) ?>
  <a class="tl-item" href="<?cs var:url ?>">
    <img class="tl-item-icon" alt="" 
          src="<?cs var:$htdocs_location + $icon ?>" />
    <span class="tl-item-time"><?cs var:item.time ?> :</span> 
    <span class="tl-item-msg"><?cs var:msg ?></span>

  </a>
  <?cs if:descr ?>
    <div class="tl-item-descr"><?cs var:descr ?></div>
  <?cs /if ?>
<?cs /def ?>

<?cs each:item = timeline.items ?>
  <?cs call:day_separator(item.date) ?>
  <div class="tl-day">
  <?cs if:item.type == #1 ?><!-- Changeset -->
    <?cs call:tlitem(item.changeset_href, 'changeset.png',
      'Changeset <b class="tl-item-link">['+$item.data+']</b>
       by '+$item.author, item.message) ?>
    <?cs elif:item.type == #2 ?><!-- New ticket -->
      <?cs call:tlitem(item.ticket_href, 'newticket.png',
        'Ticket <b class="tl-item-link">#'+$item.data+'</b>
         created by '+$item.author, item.message) ?>
    <?cs elif:item.type == #3 ?><!-- Closed ticket -->
      <?cs call:tlitem(item.ticket_href, 'closedticket.png',
        'Ticket <b class="tl-item-link">#'+$item.data+'</b>
         resolved by '+$item.author, '') ?>
    <?cs elif:item.type == #4 ?><!-- Reopened ticket -->
      <?cs call:tlitem(item.ticket_href, 'newticket.png',
        'Ticket <b class="tl-item-link">#'+$item.data+'</b>
         reopened by '+$item.author, '') ?>
    <?cs elif:item.type == #5 ?><!-- Wiki change -->
      <?cs call:tlitem(item.wiki_href, 'wiki.png',
        '<b class="tl-item-link">'+$item.data+'</b>
         edited by '+$item.author, '') ?>
    <?cs /if ?>
  </div>
<?cs /each ?>


<br />
<hr />
<div id="help">
 <strong>Note:</strong> See <a href="<?cs var:$trac.href.wiki ?>TracTimeline">TracTimeline</a> 
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
</div>
</div>
<?cs include:"footer.cs"?>


