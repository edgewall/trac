<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
        "http://www.w3.org/TR/2000/REC-xhtml1-20000126/DTD/xhtml1-strict.dtd">
<html>
 <head>
  <?cs if:project.name ?>
   <title><?cs if:title ?><?cs var:title ?> - <?cs
   /if ?><?cs var:project.name?> - Trac</title>
  <?cs else ?>
   <title>Trac: <?cs var:title ?></title>
  <?cs /if ?>
  <?cs if:html.norobots ?>
  <meta name="ROBOTS" content="NOINDEX, NOFOLLOW" />
  <?cs /if ?>
  <?cs each:rel = links ?><?cs each:link = rel ?><link rel="<?cs
   var:name(rel) ?>" href="<?cs var:link.href ?>"<?cs
   if:link.title ?> title="<?cs var:link.title ?>"<?cs /if ?><?cs
   if:link.type ?> type="<?cs var:link.type ?>"<?cs /if ?> />
  <?cs /each ?><?cs /each ?>
  <style type="text/css">
   @import url(<?cs var:htdocs_location ?>css/trac.css);
   <?cs if:html.stylesheet ?>@import url(<?cs var:htdocs_location ?><?cs
     var:html.stylesheet ?>);<?cs /if ?>
   <?cs include "site_css.cs" ?>
  </style>
  <script src="<?cs var:htdocs_location ?>trac.js" type="text/javascript"></script>
 </head>
<body>
<?cs include "site_header.cs" ?>
<div id="header">
  <a id="logo" href="<?cs var:header_logo.link ?>"><img src="<?cs var:header_logo.src ?>"
      width="<?cs var:header_logo.width ?>" height="<?cs var:header_logo.height ?>"
      alt="<?cs var:header_logo.alt ?>" /></a>
  <hr />
</div>

<form id="search" action="<?cs var:trac.href.search ?>" method="get">
 <?cs if:trac.acl.SEARCH_VIEW ?><div>
  <label for="proj-search">Search:</label>
  <input type="text" id="proj-search" name="q" size="10" value="" />
  <input type="submit" value="Search" />
  <input type="hidden" name="wiki" value="on" />
  <input type="hidden" name="changeset" value="on" />
  <input type="hidden" name="ticket" value="on" />
 </div><?cs /if ?>
</form>

<div id="metanav" class="nav">
 <h2>Navigation</h2>
 <ul>
  <li><?cs if:trac.authname == "anonymous" || !trac.authname ?>
    <a href="<?cs var:trac.href.login ?>">Login</a>
  <?cs else ?>
    logged in as <?cs var:trac.authname ?> </li>
    <li><a href="<?cs var:trac.href.logout ?>">Logout</a>
  <?cs /if ?></li>
  <li><a href="<?cs var:trac.href.settings ?>">Settings</a></li>
  <li><a accesskey="6" href="<?cs var:trac.href.wiki ?>/TracGuide">Help/Guide</a></li>
  <li style="display: none"><a accesskey="5" href="http://projects.edgewall.com/trac/wiki/TracFaq">FAQ</a></li>
  <li style="display: none"><a accesskey="0" href="<?cs var:trac.href.wiki ?>/TracAccessibility">Accessibility</a></li>
  <li class="last"><a accesskey="9" href="<?cs var:trac.href.about ?>">About Trac</a></li>
 </ul>
</div>

<?cs def:navlink(text, href, id, aclname, accesskey) ?><?cs
 if $error.type || $aclname ?><li><a href="<?cs var:href ?>" <?cs 
  if $id == $trac.active_module ?>class="active"<?cs
  /if ?><?cs
  if:$accesskey!="" ?> accesskey="<?cs var:$accesskey ?>"<?cs 
  /if ?>><?cs var:text ?></a></li><?cs 
 /if ?><?cs
/def ?>

<?cs if $trac.active_module == "wiki" ?><?cs
  set:$wiki_view="wiki" ?><?cs
 else  ?><?cs
  set:$wiki_view="attachment" ?><?cs
 /if  ?><?cs
 if $trac.active_module == "ticket" ?><?cs
  set:$ticket_view="ticket" ?><?cs
 elif $trac.active_module == "query" ?><?cs
  set:$ticket_view="query" ?><?cs
 else ?><?cs
  set:$ticket_view="report" ?><?cs
 /if  ?><?cs
 if $trac.active_module == "log" ?><?cs
  set:$browser_view="log" ?><?cs
 elif $trac.active_module == "file" ?><?cs
  set:$browser_view="file" ?><?cs
 else  ?><?cs
  set:$browser_view="browser" ?><?cs
 /if  ?><?cs
 if $trac.active_module == "milestone" ?><?cs
  set:$roadmap_view="milestone" ?><?cs
 else ?><?cs
  set:$roadmap_view="roadmap" ?><?cs 
 /if ?>

<div id="mainnav" class="nav">
 <ul>
  <?cs call:navlink("Wiki", $trac.href.wiki, $wiki_view,
                    $trac.acl.WIKI_VIEW, "1") ?>
  <?cs call:navlink("Timeline", $trac.href.timeline, "timeline",
                    $trac.acl.TIMELINE_VIEW, "2") ?>
  <?cs call:navlink("Roadmap", trac.href.roadmap, $roadmap_view,
                    $trac.acl.ROADMAP_VIEW, "") ?>
  <?cs call:navlink("Browse Source", $trac.href.browser, $browser_view,
                    $trac.acl.BROWSER_VIEW, "") ?>
  <li style="display: none"><a href="<?cs var:$trac.href.newticket ?>"
                    accesskey="7">New Ticket (Accessibility)</a></li>
  <?cs call:navlink("View Tickets", $trac.href.report, $ticket_view,
                    $trac.acl.REPORT_VIEW, "") ?>
  <?cs call:navlink("New Ticket", $trac.href.newticket, "newticket",
                    $trac.acl.TICKET_CREATE, "9") ?>
  <?cs call:navlink("Search", $trac.href.search, "search",
                    $trac.acl.SEARCH_VIEW, "4") ?>
 </ul>
</div>

<div id="main">
