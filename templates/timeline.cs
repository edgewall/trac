<?cs include "header.cs"?>
<div id="page-content">
 <div id="subheader-links">
   <br />
 </div>

<div id="main">
  <div id="main-content">

<h1 id="timeline-hdr">Timeline</h1>

<form action="<?cs var:trac.href.timeline ?>">
  <div id="timeline-prefs">
    View changes from 
    <input size="10" name="from" value="<?cs var:timeline.from ?>" /> 
    and 
    <input size="3" name="daysback" value="<?cs var:timeline.daysback ?>" />
    days back:
  <div id="timeline-prefs-checks">
    <input type="checkbox" name="ticket" <?cs var:timeline.ticket ?> />
    view ticket changes
  <br />
    <input type="checkbox" name="changeset" <?cs var:timeline.changeset ?> />
    view repository checkins
  <br />
    <input type="checkbox" name="wiki" <?cs var:timeline.wiki ?> />
   view wiki changes
  </div>
  <div id="timeline-prefs-btns">
    <input type="submit" value="Update" /> 
    <input type="reset" />
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
         closed by '+$item.author, '') ?>
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

 </div>
</div>
</div>
<?cs include:"footer.cs"?>


