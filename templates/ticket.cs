<?cs include "header.cs" ?>
<?cs include "macros.cs" ?>
<div id="page-content">
<div id="subheader-links">
<br />
</div>

 <div id="main">
  <div id="main-content">

<?cs if:ticket.status == 'closed' ?>
 <?cs set:status = ' (Closed: ' + $ticket.resolution + ')' ?>
<?cs elif:ticket.status == 'new' ?>
<?cs else ?>
 <?cs set:status = ' (' + ticket.status + ')' ?>
<?cs /if ?>

<h1 id="tkt-hdr">Ticket #<?cs var:ticket.id ?><?cs var:status ?></h1>

<div id="tkt-ticket">
  <span id="tkt-date">
    <?cs var:ticket.opened ?>
  </span>
  <h2 id="tkt-summary">
    #<?cs var:ticket.id ?> : <?cs var:ticket.summary ?>
  </h2>

<?cs def:ticketprop(label, value) ?>
<div class="tkt-prop">
    <b class="tkt-label"><?cs var:label ?>:</b>&nbsp;
    <?cs if:value ?>
      <em class="tkt-val"><?cs var:value ?></em>
    <?cs else ?>
      <br />
    <?cs /if ?>
  </div>
<?cs /def ?>

<div id="tkt-left">
  <?cs call:ticketprop("Priority", ticket.priority) ?>
  <?cs call:ticketprop("Severity", ticket.severity) ?>
  <?cs call:ticketprop("Component", ticket.component) ?>
  <?cs call:ticketprop("Version", ticket.version) ?>
  <?cs call:ticketprop("Milestone", ticket.milestone) ?>
</div>
<div id="tkt-right">
  <?cs call:ticketprop("Reporter", ticket.reporter) ?>
  <?cs if ticket.status == "assigned"?>
  <?cs call:ticketprop("Assigned to", ticket.owner + " (accepted)") ?>
  <?cs else ?>
  <?cs call:ticketprop("Assigned to", ticket.owner) ?>
  <?cs /if ?>
  <?cs call:ticketprop("Status", ticket.status) ?>
  <?cs call:ticketprop("Resolution", ticket.resolution) ?>
</div>

<br style="clear: both" />

<div id="tkt-descr">
  <b>Description by <?cs var:ticket.reporter ?>:
  </b>
  <br />
  <?cs var:ticket.description ?>
</div>

</div> <!-- #tkt-ticket -->

<hr class="hide"/>
<?cs if ticket.changes.0.time ?>
  <h2 id="tkt-changes-hdr">Changelog</h2>
  <div id="tkt-changes">
    <?cs set:numchanges = 0 ?>
    <?cs set:comment = "" ?>
    <?cs set:curr_time = "" ?>
    <?cs set:curr_author = "" ?>
    <?cs each:item = ticket.changes ?>
      <?cs set:numchanges = #numchanges + 1 ?>
      <?cs if $item.time != $curr_time || $item.author != $curr_author ?>
        <?cs if $comment != "" ?>
          <li class="tkt-chg-change">
            <h4 class="tkt-chg-comment-hdr">Comment:</h4>
            <div  class="tkt-chg-comment"><?cs var:$comment ?></div>
            <?cs set:comment = "" ?>
          </li>
        <?cs /if ?>
        <?cs set:curr_time = $item.time ?>
        <?cs set:curr_author = $item.author ?>
        <?cs if:#numchanges > 1 ?>
          </ul>
        <?cs /if ?>
        <h3 class="tkt-chg-mod">
          <a name="<?cs var:#numchanges ?>"><?cs var:item.date ?> : Modified by <?cs var:curr_author ?></a>
        </h3>
        <ul class="tkt-chg-list">
      <?cs /if ?>
      <?cs if $item.field == "comment" ?>
      <?cs set:$comment = $item.new ?> 
      <?cs elif $item.new == "" ?>
        <li class="tkt-chg-change">
           cleared <b><?cs var:item.field?></b>
        </li>
      <?cs elif $item.old == "" ?>
        <li class="tkt-chg-change">
          <b><?cs var:item.field ?></b> set to <b><?cs var:item.new ?></b>
        </li>
      <?cs else ?>
        <li class="tkt-chg-change">
           <b><?cs var:item.field ?></b> changed from
           <b><?cs var:item.old ?></b> to
           <b><?cs var:item.new ?></b>
        </li>
      <?cs /if ?>
    <?cs /each ?>
    <?cs if $comment != "" ?>
       <li class="tkt-chg-change">
         <h4 class="tkt-chg-comment-hdr">Comment:</h4>
         <div  class="tkt-chg-comment"><?cs var:$comment ?></div>
       </li>
     <?cs /if ?>
    </ul>
  </div>
<?cs /if ?>
<hr class="hide"/>


<form action="<?cs var:cgi_location ?>" method="post">
<h3>Add/Change Information</h3>
  <div id="nt-props-left">
    <input type="hidden" name="mode" value="ticket" />
    <input type="hidden" name="id"   value="<?cs var:ticket.id ?>" />

    <div class="nt-prop">
      <span class="nt-label">Opened:</span>
      <span class="nt-widget">
        <?cs var:ticket.opened ?>
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Version:</span>
      <span class="nt-widget">
        <?cs call:hdf_select(ticket.versions, "version",
                             ticket.version) ?>
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Component:</span>
      <span class="nt-widget">
        <?cs call:hdf_select(ticket.components, "component",
                             ticket.component) ?>
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Severity:</span>
      <span class="nt-widget">
        <?cs call:hdf_select(enums.severity, "severity",
                             ticket.severity) ?>
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Status:</span>
      <span class="nt-widget"><?cs var:ticket.status ?></span>
    </div>
    <?cs if:ticket.resolution ?>
      <div class="nt-prop">
        <span class="nt-label">Resolution:</span>
        <span class="nt-widget"><?cs var:ticket.resolution ?></span>
      </div>
    <?cs /if ?>

  </div>
  <div id="nt-props-right">
    <div class="nt-prop">
      <span class="nt-label">Reporter:</span>
      <span class="nt-widget">
        <input type="text" name="reporter"
              value="<?cs var:trac.authname ?>" />
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Priority:</span>
      <span class="nt-widget">
        <?cs call:hdf_select(enums.priority, "priority",
                             ticket.priority) ?>
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Milestone:</span>
      <span class="nt-widget">
        <?cs call:hdf_select(ticket.milestones, "milestone",
                             ticket.milestone) ?>
      </span>
    </div>
    <?cs if:ticket.owner ?>
      <div class="nt-prop">
        <span class="nt-label">Assigned To:</span>
        <span class="nt-widget"><?cs var:ticket.owner ?></span>
      </div>
    <?cs /if ?>
  </div>
  <div><br style="clear: both" /></div>
  <div id="nt-props-middle">
    <div class="nt-prop">
      <span class="nt-label">Cc:</span>
      <span class="nt-widget">
         <input type="text" name="cc" value="<?cs var:ticket.cc ?>" />
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">
        <a href="<?cs var:ticket.url ?>">URL</a>:
      </span>
      <span class="nt-widget">
        <input type="text" name="url"
                value="<?cs var:ticket.url ?>" size="50" />
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Summary</span>
      <span class="nt-widget">
        <input type="text" name="summary"
                value="<?cs var:ticket.summary ?>" size="50" />
      </span>
    </div>
  </div>
  <div><br style="clear: both" /></div>
  <div id="nt-props-bottom">
    <div class="nt-prop">
      <div class="nt-label">Additional Comments:</div>
      <br style="clear: both"/>
      <span class="nt-widget" style="clear: both">
        <textarea name="comment" rows="10" cols="66"></textarea>
      </span>
    <div id="nt-submit2">
  <input type="radio" name="action" value="leave" checked="checked" />
  &nbsp;leave as <?cs var:ticket.status ?><br />
 
  <?cs if $ticket.status == "new" ?>
    <input type="radio" name="action" value="accept" />
    &nbsp;accept ticket<br />
  <?cs /if ?>
  <?cs if $ticket.status == "closed" ?>
    <input type="radio" name="action" value="reopen" />
    &nbsp;reopen ticket<br />
  <?cs /if ?>
  <?cs if $ticket.status == "new" || $ticket.status == "assigned" || $ticket.status == "reopened" ?>
    <input type="radio" name="action" value="resolve" />
    &nbsp;resolve as: 
    <select name="resolve_resolution">
      <option selected="selected">fixed</option>
      <option>invalid</option>
      <option>wontfix</option>
      <option>duplicate</option>
      <option>worksforme</option>
    </select><br />
    <input type="radio" name="action" value="reassign" />
    &nbsp;reassign ticket to:
    &nbsp;<input type="text" name="reassign_owner" 
          value="<?cs var:ticket.owner ?>" />
  <?cs /if ?>
<br />
<input type="submit" value="commit" /> 
    </div>
    </div>
  </div>
</form>


 </div>
</div>
</div>
<?cs include:"footer.cs"?>

