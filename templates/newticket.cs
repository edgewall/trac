<?cs include "header.cs" ?>
<?cs include "macros.cs" ?>

<div id="page-content">
<div id="subheader-links">
<br />
</div>
 <div id="main">
  <div id="main-content">

<h3>Create New Ticket:</h3>
<form action="<?cs var:cgi_location ?>" method="post">
 <table id="nt-upper">
  <tr class="nt-prop">
   <td class="nt-label">Reporter:</td>
   <td class="nt-widget">
    <input type="hidden" name="mode" value="ticket" />
    <input type="hidden" name="action" value="create" />
    <input type="hidden" name="status" value="new" />
    <input type="text" name="reporter" value="<?cs var:trac.authname ?>" />
   </td>
   <td class="nt-prop-sep">&nbsp;</td>
   <td class="nt-label">Priority:</td>
   <td class="nt-widget">
    <?cs call:hdf_select(enums.priority, "priority", 
                         newticket.default_priority) ?>
   </td>
  </tr>
  <tr class="nt-prop">
   <td class="nt-label">Component:</td>
   <td class="nt-widget">
    <?cs call:hdf_select(newticket.components, "component",
                        newticket.default_component) ?>
   </td>
   <td class="nt-prop-sep">&nbsp;</td>
   <td class="nt-label">Milestone:</td>
   <td class="nt-widget">
    <?cs call:hdf_select(newticket.milestones, "milestone",
                         newticket.default_milestone) ?>
   </td>
  </tr>
  <tr class="nt-prop">
   <td class="nt-label">Version:</td>
   <td class="nt-widget">
    <?cs call:hdf_select(newticket.versions, "version",
                         newticket.default_version) ?>
   </td>
   <td class="nt-prop-sep">&nbsp;</td>
   <td class="nt-label">Assign to:</td>
   <td class="nt-widget"><input type="text" name="owner" /></td>
  </tr>
  <tr class="nt-prop">
   <td class="nt-label">Severity:</td>
    <td class="nt-widget">
     <?cs call:hdf_select(enums.severity, "severity",
                          newticket.default_severity) ?>
    </td>
   <td class="nt-prop-sep">&nbsp;</td>
    <td class="nt-label"></td>
    <td class="nt-widget"></td>
   </tr>
 <tr>
  <td colspan="2" class="nt-row-sep">&nbsp;</td>
  <td class="nt-prop-sep">&nbsp;</td>
  <td colspan="2" class="nt-row-sep">&nbsp</td>
</tr>
</table>

<table id="nt-lower">
 <tr>
  <td class="nt-label">Cc:</td>
  <td class="nt-widget">
   <input type="text" name="cc" size="66" />
  </td>
 </tr>
 <tr>
  <td class="nt-label">URL:</td>
  <td class="nt-widget">
   <input type="text" name="url" size="66" />
  </td>
 </tr>
 <tr>
  <td class="nt-label">Summary:</td>
  <td class="nt-widget">
   <input type="text" name="summary" size="66" />
  </td>
 </tr>
 <tr><td colspan="2" id="nt-row-sep">&nbsp;<hr class="hide" /></td></tr>
 <tr>
  <td colspan="2" id="nt-descr">Description:</td>
 </tr>
 <tr>
  <td colspan="2" class="nt-widget">
        <textarea name="description" rows="11" cols="78"></textarea>
  </td>
 </tr>
 <tr>
  <td colspan="2" id="nt-submit">
   <input type="reset" value="Reset" />&nbsp;
   <input type="submit" value="Submit ticket" />
  </td>
 </tr>
</table>
</form>

<div id="help">
 <strong>Note:</strong> See <a href="<?cs var:$trac.href.wiki
?>TracTickets">TracTickets</a> for help on using tickets.
</div>
 </div>
</div>
</div>
<?cs include "footer.cs" ?>
