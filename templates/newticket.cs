<?cs include "header.cs" ?>
<?cs include "macros.cs" ?>
<div id="page-content">
<div id="subheader-links">
<br />
</div>
 <div id="main">
  <div id="main-content">

<h3>New ticket:</h3>

<form action="<?cs var:cgi_location ?>" method="post">
  <div id="nt-props-left">
    <input type="hidden" name="mode" value="ticket" />
    <input type="hidden" name="action" value="create" />
    <input type="hidden" name="status" value="new" />
    <div class="nt-prop">
      <span class="nt-label">Reporter:</span>
      <span class="nt-widget">
        <input type="text" name="reporter"
              value="<?cs var:newticket.reporter ?>" />
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Component:</span>
      <span class="nt-widget">
        <?cs call:hdf_select(newticket.components, "component",
             newticket.default_component) ?>
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Version:</span>
      <span class="nt-widget">
        <?cs call:hdf_select(newticket.versions, "version",
             newticket.default_version) ?>
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Severity:</span>
      <span class="nt-widget">
        <?cs call:hdf_select(enums.severity, "severity",
             newticket.default_severity) ?>
      </span>
    </div>
  </div>
  <div id="nt-props-right">
    <div class="nt-prop">
    <span class="nt-label">Priority:</span>
      <span class="nt-widget">
        <?cs call:hdf_select(enums.priority, "priority", "p2") ?>
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Milestone:</span>
      <span class="nt-widget">
        <?cs call:hdf_select(newticket.milestones, "milestone",
             newticket.default_milestone) ?>
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Assign to:</span>
      <span class="nt-widget"><input type="text" name="owner" /></span>
    </div>
  </div>
  <div id="nt-props-middle">
    <div class="nt-prop">
      <span class="nt-label">Cc:</span>
      <span class="nt-widget">
        <input type="text" name="cc" size="50" />
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">URL:</span>
      <span class="nt-widget">
        <input type="text" name="url" size="50" />
      </span>
    </div>
    <div class="nt-prop">
      <span class="nt-label">Summary:</span>
      <span class="nt-widget">
        <input type="text" name="summary" size="50" />
      </span>
    </div>
  </div>
  <div id="nt-props-bottom">
    <div class="nt-prop">
      <span class="nt-label">Description:</span>
      <span class="nt-widget">
        <textarea name="description" rows="10" cols="66"></textarea>
      </span>
    </div>
    <div id="nt-submit">
      <input type="reset" value="reset" />&nbsp;
      <input type="submit" value="commit" />
    </div>
  </div>
</form>

 </div>
</div>
</div>
<?cs include "footer.cs" ?>
