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
    <input type="checkbox" name="ticket" checked="<?cs var:timeline.ticket ?>" />
    view ticket changes
  <br />
    <input type="checkbox" name="changeset" checked="<?cs var:timeline.changeset ?>" />
    view repository checkins
  <br />
    <input type="checkbox" name="wiki" checked="<?cs var:timeline.wiki ?>" />
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

<?cs each:item = timeline.items ?>
  <?cs call:day_separator(item.date) ?>
    <div class="tl-item">
<!-- Changeset -->
  <?cs if:item.type == #1 ?>
    <a class="tl-item-chgset" href="<?cs var:item.changeset_href ?>">
      <img class="tl-item-icon" alt="" 
            src="<?cs var:htdocs_location?>/changeset.png" />
      <span class="tl-item-time"><?cs var:item.time?></span>
      <span class="tl-item-data">
        Changeset <b>[<?cs var:item.data?>]</b> by <?cs var:item.author ?>:
      </span>
      <span class="tl-item-descr"><?cs var:item.message?></span>
    </a>
<!-- New ticket -->
  <?cs elif:item.type == #2 ?>
      <a class="tl-item-newtkt" href="<?cs var:item.ticket_href ?>">
        <img class="tl-item-icon" alt="" 
              src="<?cs var:htdocs_location?>/newticket.png" />
        <span class="tl-item-time"><?cs var:item.time?></span>
        <span class="tl-item-data">
          Ticket <b>#<?cs var:item.data?></b> created by <?cs var:item.author ?>:
        </span>
        <span class="tl-item-descr"><?cs var:item.message?></span>
      </a>
<!-- Closed ticket -->
  <?cs elif:item.type == #3 ?>
      <a class="tl-item-closedtkt" href="<?cs var:item.ticket_href ?>">
        <img class="tl-item-icon" alt=""
              src="<?cs var:htdocs_location?>/closedticket.png" />
        <span class="tl-item-time"><?cs var:item.time?></span>
        <span class="tl-item-data">
          Ticket <b>#<?cs var:item.data?></b> closed by
          <?cs var:item.author ?>.
        </span>
      </a>
<!-- Reopened ticket -->
  <?cs elif:item.type == #4 ?>
    <a class="tl-item-reopentkt" href="<?cs var:item.ticket_href ?>">
      <img class="tl-item-icon" alt=""
            src="<?cs var:htdocs_location?>/newticket.png" />
      <span class="tl-item-time"><?cs var:item.time?></span>
      <span class="tl-item-data">
        Ticket <b>#<?cs var:item.data?></b> reopened by <?cs var:item.author ?>.
      </span>
    </a>
<!-- Wiki change -->
  <?cs elif:item.type == #5 ?>
    <a class="tl-item-wiki" href="<?cs var:item.wiki_href ?>">
      <img class="tl-item-icon" alt=""
            src="<?cs var:htdocs_location?>/wiki.png" />
      <span class="tl-item-time"><?cs var:item.time?></span>
      <span class="tl-item-data">
        <b><?cs var:item.data?></b> edited by <?cs var:item.author ?>.
      </span>
    </a>
  <?cs /if ?>
    </div>
<?cs /each ?>


 </div>
</div>
</div>
<?cs include:"footer.cs"?>


