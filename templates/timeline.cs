<?cs set:html.stylesheet = 'css/timeline.css' ?>
<?cs include "header.cs"?>

<div id="ctxtnav" class="nav"></div>

<div id="content" class="timeline">
<h1>Timeline</h1>

<form id="prefs" action="">
 <div>
  <label>View changes from <input type="text" size="10" name="from" value="<?cs
    var:timeline.from ?>" /></label> and
  <label><input type="text" size="3" name="daysback" value="<?cs
    var:timeline.daysback ?>" /> days back</label>.
 </div>
 <fieldset><?cs
  each:filter = timeline.filters ?>
   <label><input type="checkbox" name="<?cs var:filter.name ?>"<?cs
     if:filter.enabled ?> checked="checked"<?cs /if ?> /> <?cs
     var:filter.label ?></label><?cs
  /each ?>
 </fieldset>
 <div class="buttons">
  <input type="submit" value="Update" />
 </div>
</form><?cs

def:day_separator(date) ?><?cs
 if:date != current_date ?><?cs
  if:current_date ?></dl><?cs /if ?><?cs
  set:current_date = $date ?>
  <h2><?cs var:date ?>:</h2><dl><?cs
 /if ?><?cs
/def ?><?cs

def:tlitem(url, type, msg, descr) ?>
 <dt class="<?cs var:type ?>">
  <a href="<?cs var:url ?>"><span class="time"><?cs
    var:item.time ?></span> <?cs var:msg ?></a>
 </dt><?cs
 if:descr ?><dd><?cs var:descr ?></dd><?cs
 /if ?><?cs
/def ?><?cs

each:item = timeline.items ?><?cs
 call:day_separator(item.date) ?><?cs
 if:item.type == 'changeset' ?><?cs
  call:tlitem(item.href, 'changeset',
              'Changeset <em>[' + item.idata + ']</em> by ' + item.author,
              item.node_list + item.message) ?><?cs
 elif:item.type == 'newticket' ?><?cs
  call:tlitem(item.href, 'newticket',
              'Ticket <em>#' + item.idata + '</em> created by ' + item.author,
              item.message) ?><?cs
 elif:item.type == 'closedticket' ?><?cs
  if:item.message ?><?cs
   set:imessage = ' - ' + item.message ?><?cs
  else ?><?cs
   set:imessage = '' ?><?cs
  /if ?><?cs
  call:tlitem(item.href, 'closedticket',
              'Ticket <em>#' + item.idata + '</em> resolved by ' + item.author,
              item.tdata + imessage) ?><?cs
 elif:item.type == 'reopenedticket' ?><?cs
  call:tlitem(item.href, 'newticket',
              'Ticket <em>#' + item.idata + '</em> reopened by ' + item.author,
              '') ?><?cs
 elif:item.type == 'wiki' ?><?cs
  call:tlitem(item.href, 'wiki',
              '<em>' + item.tdata + '</em> edited by ' + item.author,
              item.message) ?><?cs
 elif:item.type == 'milestone' ?><?cs
  call:tlitem(item.href, 'milestone',
              '<em>Milestone ' + item.tdata + '</em> reached', '') ?><?cs
 /if ?><?cs
/each ?><?cs
if:len(timeline.items) ?></dl><?cs /if ?>

<div id="help">
 <hr />
 <strong>Note:</strong> See <a href="<?cs var:trac.href.wiki ?>/TracTimeline">TracTimeline</a> 
 for information about the timeline view.
</div>

</div>
<?cs include "footer.cs"?>
