<?cs include "header.cs" ?>
<?cs include "macros.cs" ?>
<script type="text/javascript">
addEvent(window, 'load', function() { document.getElementById('summary').focus()}); 
</script>
<div id="page-content">
<div id="subheader-links">
<br />
</div>
 <div id="main">
  <div id="main-content">

<h3>Create New Ticket:</h3>
<div id="nt-ticket">
<form action="<?cs var:cgi_location ?>" method="post">

 <div id="nt-body">
  <div class="tkt-prop">
   <label for="reporter">Your email or username:</label><br />
   <input type="text" id="reporter" name="reporter" size="40"
           class="textwidget" value="<?cs var:trac.authname ?>" /><br />
  </div>
  <div class="tkt-prop">
   <label for="summary">Short Summary:</label>&nbsp;<br />
   <input id="summary" type="text" name="summary" class="textwidget" size="80"/>
  </div>
  <div class="tkt-prop">
   <label for="description">Full Description (You may use 
      <a tabindex="42" href="<?cs var:$trac.href.wiki ?>WikiFormatting">WikiFormatting</a> here):</label><br />
   <textarea id="description" name="description" class="textwidget" 
            rows="10" cols="78" style="width: 97%"></textarea>
  </div>
 </div>

<fieldset>
 <legend>Ticket Properties</legend>
 <div id="nt-props">
  <div id="nt-left">
  <input type="hidden" name="mode" value="ticket" />
  <input type="hidden" name="action" value="create" />
  <input type="hidden" name="status" value="new" />
   <label for="component" class="nt-label">Component:</label>
   <?cs call:hdf_select(newticket.components, "component",
                        newticket.default_component) ?><br />
   <label for="version" class="nt-label">Version:</label>
   <?cs call:hdf_select(newticket.versions, "version",
                        newticket.default_version) ?><br />
   <label for="severity" class="nt-label">Severity:</label>
    <?cs call:hdf_select(enums.severity, "severity",
                         newticket.default_severity) ?><br />
  <label for="keywords" class="nt-label">Keywords:</label>
   <input type="text" id="keywords" name="keywords" size="28" class="textwidget" 
          value="" /><br />
  </div>
 <div  id="nt-right" style="">
  <label for="priority" class="nt-label">Priority:</label>
  <?cs call:hdf_select(enums.priority, "priority", 
                       newticket.default_priority) ?><br />
  <label for="milestone" class="nt-label">Milestone:</label>
  <?cs call:hdf_select(newticket.milestones, "milestone",
                       newticket.default_milestone) ?><br />
  <label for="owner" class="nt-label">Assign to:</label>
   <input type="text" id="owner" name="owner" size="35" class="textwidget" 
          value="<?cs var:newticket.default_owner ?>" /><br />
  <label for="cc" class="nt-label">Cc:</label>
   <input type="text" id="cc" name="cc" size="35" class="textwidget" 
	value="" /><br />
  </div>
 </div>
 </fieldset>

 <div id="nt-buttons">
  <input type="reset" value="Reset" />&nbsp;
  <input type="submit" value="Submit ticket" />
 </div>

</form>

 <div id="help">
  <strong>Note:</strong> See <a href="<?cs var:$trac.href.wiki
  ?>TracTickets">TracTickets</a> for help on using tickets.
 </div>
</div> <!-- #nt-ticket -->

 </div>
</div>
</div>

<?cs include "footer.cs" ?>

