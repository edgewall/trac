<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
<title>Edgewall SVNTRAC - <?cs var:title ?></title>
<link rel="stylesheet" type="text/css" href="<?cs var:htdocs_location ?>/svntrac.css">
</head>
<body marginheight="0" marginwidth="0" rightmargin="0" leftmargin="0" 
topmargin="0" bottommargin="0" link="#aa0000" alink="#cc0000" vlink="#880000">
    <div id="page-header">
      <table bgcolor="#eeeeee" 
	background="<?cs var:htdocs_location ?>topbar_gradient.png" 
	id="page-topbar" border="0" 
	cellspacing="0" cellpadding="0" width="100%">
	  <tr>
	    <td align="right" class="topbar">
	      <a href="http://www.edgewall.com/press/" class="topbar-link">Press Center</a> |
	      <a href="http://www.edgewall.com/company/" class="topbar-link">Company</a> |
	      <a href="http://www.edgewall.com/contact/" class="topbar-link">Contact</a>
	    </td>
	  </tr>
      </table>
      <table id="page-header" border="0" cellspacing="0" 
	cellpadding="0" width="100%">
	  <tr>
	    <td bgcolor="white" width="100%" style="white-space:nowrap">
	      <a href="http://svntrac.edgewall.com/">
		<img src="<?cs var:htdocs_location ?>svntrac_logo.png" 
		  width="500" height="70" alt="svntrac" border="0" 
		  hspace="0" vspace="0" />
	      </a>
	    </td>
	  </tr>
      </table>
    </div>
<!-- <?cs var:toolbar ?> -->

<!-- Toolbar -->
<?cs def:link(text, href, id) ?>
  <?cs if $id == $svntrac.active_module ?>
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
      <?cs if ? $svntrac.acl.WIKI_VIEW ?>
        <?cs call:link("Wiki", $svntrac.href.wiki, "wiki") ?>
      <?cs /if ?>
      <?cs if ? $svntrac.acl.BROWSER_VIEW ?>
        <?cs call:link("Browse", $svntrac.href.browser, "browser") ?>
      <?cs /if ?>
      <?cs if ? $svntrac.acl.TIMELINE_VIEW ?>
        <?cs call:link("Timeline", $svntrac.href.timeline, "timeline") ?>
      <?cs /if ?>
      <?cs if ? $svntrac.acl.REPORT_VIEW ?>
        <?cs call:link("Reports", $svntrac.href.report, "report") ?>
      <?cs /if ?>
      <?cs if ? $svntrac.acl.SEARCH_VIEW ?>
        <?cs call:link("Search", $svntrac.href.search, "search") ?>
      <?cs /if ?>
      <?cs if ? $svntrac.acl.TICKET_CREATE ?>
        <?cs call:link("New Ticket", $svntrac.href.newticket, "newticket") ?>
      <?cs /if ?>
    </td>
    <td class="navbar" align="right">
      <?cs if $svntrac.authname == "anonymous" ?>
	 <a href="<?cs var:svntrac.href.login ?>" class="navbar-link-right">
	      login
	 </a>
      <?cs else ?>
	logged in as <?cs var:svntrac.authname ?>&nbsp;
	 <a href="<?cs var:svntrac.href.logout ?>" class="navbar-link-right">
	      logout
	 </a>
      <?cs /if ?>
    </td>
  </tr>
</table>
<div id="page-content">
