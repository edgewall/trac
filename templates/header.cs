<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
<title>Edgewall Trac <?cs var:title ?></title>
<link rel="stylesheet" type="text/css" href="<?cs var:htdocs_location ?>/trac.css">
</head>
<body marginheight="0" marginwidth="0" rightmargin="0" leftmargin="0" 
  topmargin="0" bottommargin="0" 
  link="#aa0000" alink="#cc0000" vlink="#880000">

    <div id="page-header">
      <table id="page-header" border="0" cellspacing="0" 
	cellpadding="0" width="100%">
	  <tr>
	    <td bgcolor="white" width="100%" style="white-space:nowrap">
	      <a href="<?cs var:header_logo.link ?>">
		<img src="<?cs var:header_logo.src ?>" 
		  width="<?cs var:header_logo.width ?>" 
		  height="<?cs var:header_logo.height ?>" 
		  alt="<?cs var:header_logo.alt ?>" border="0" 
		  hspace="0" vspace="0" />
	      </a>
	    </td>
	  </tr>
      </table>
    </div>
    
<!-- Toolbar -->
<?cs def:link(text, href, id) ?>
  <?cs if $id == $trac.active_module ?>
    <a href="<?cs var:href ?>" class="navbar-link-active"><?cs var:text ?></a>
  <?cs else ?>
    <a href="<?cs var:href ?>" class="navbar-link"><?cs var:text ?></a>
  <?cs /if ?>
<?cs /def ?>

<table width="100%" cellspacing="0" cellpadding="0" id="page-navbar" 
 cellpadding="10" bgcolor="black" 
 background="<?cs var:htdocs_location ?>navbar_gradient.png">
  <tr>
    <td class="navbar">
      <?cs if ? $trac.acl.WIKI_VIEW ?>
        <?cs call:link("Wiki", $trac.href.wiki, "wiki") ?>
      <?cs /if ?>
      <?cs if ? $trac.acl.BROWSER_VIEW ?>
        <?cs call:link("Browse", $trac.href.browser, "browser") ?>
      <?cs /if ?>
      <?cs if ? $trac.acl.TIMELINE_VIEW ?>
        <?cs call:link("Timeline", $trac.href.timeline, "timeline") ?>
      <?cs /if ?>
      <?cs if ? $trac.acl.REPORT_VIEW ?>
        <?cs call:link("Reports", $trac.href.report, "report") ?>
      <?cs /if ?>
      <?cs if ? $trac.acl.SEARCH_VIEW ?>
        <?cs call:link("Search", $trac.href.search, "search") ?>
      <?cs /if ?>
      <?cs if ? $trac.acl.TICKET_CREATE ?>
        <?cs call:link("New Ticket", $trac.href.newticket, "newticket") ?>
      <?cs /if ?>
    </td>
    <td class="navbar" align="right">
      <?cs if $trac.authname == "anonymous" ?>
	 <a href="<?cs var:trac.href.login ?>" class="navbar-link-right">
	      login
	 </a>
      <?cs else ?>
	logged in as <?cs var:trac.authname ?>&nbsp;
	 <a href="<?cs var:trac.href.logout ?>" class="navbar-link-right">
	      logout
	 </a>
      <?cs /if ?>
    </td>
  </tr>
</table>
<div id="page-content">
