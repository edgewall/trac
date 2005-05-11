<!DOCTYPE html
    PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head><?cs
 if:project.name ?>
 <title><?cs if:title ?><?cs var:title ?> - <?cs /if ?><?cs
   var:project.name?> - Trac</title><?cs
 else ?>
 <title>Trac: <?cs var:title ?></title><?cs
 /if ?><?cs
 if:html.norobots ?>
 <meta name="ROBOTS" content="NOINDEX, NOFOLLOW" /><?cs
 /if ?><?cs
 each:rel = chrome.links ?><?cs
  each:link = rel ?><link rel="<?cs
   var:name(rel) ?>" href="<?cs var:link.href ?>"<?cs
   if:link.title ?> title="<?cs var:link.title ?>"<?cs /if ?><?cs
   if:link.type ?> type="<?cs var:link.type ?>"<?cs /if ?> /><?cs
  /each ?><?cs
 /each ?><style type="text/css"><?cs include:"site_css.cs" ?></style>
 <script src="<?cs var:htdocs_location ?>js/trac.js" type="text/javascript"></script>
</head>
<body>
<?cs include "site_header.cs" ?>
<div id="banner">

<div id="header"><a id="logo" href="<?cs
 var:chrome.logo.link ?>"><img src="<?cs var:chrome.logo.src ?>" width="<?cs
 var:chrome.logo.width ?>" height="<?cs var:chrome.logo.height ?>" alt="<?cs
 var:chrome.logo.alt ?>" /></a><hr />
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

<?cs def:nav(items) ?><?cs
 if:len(items) ?><ul><?cs
  set:idx = 0 ?><?cs
  set:max = len(items) - 1 ?><?cs
  each:item = items ?><?cs
   set:first = idx == 0 ?><?cs
   set:last = idx == max ?><li<?cs
   if:first || last || item.active ?> class="<?cs
    if:item.active ?>active<?cs /if ?><?cs
    if:item.active && (first || last) ?> <?cs /if ?><?cs
    if:first ?>first<?cs /if ?><?cs
    if:(item.active || first) && last ?> <?cs /if ?><?cs
    if:last ?>last<?cs /if ?>"<?cs
   /if ?>><?cs var:item ?></li><?cs
   set:idx = idx + 1 ?><?cs
  /each ?></ul><?cs
 /if ?><?cs
/def ?>

<div id="metanav" class="nav"><?cs call:nav(chrome.nav.metanav) ?></div>
</div>

<div id="mainnav" class="nav"><?cs call:nav(chrome.nav.mainnav) ?></div>
<div id="main">
