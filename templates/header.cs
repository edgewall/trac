<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
        "http://www.w3.org/TR/2000/REC-xhtml1-20000126/DTD/xhtml1-strict.dtd">

<?cs def:navlink(text, href, id, aclname, accesskey) ?><?cs
   if $trac.acl.+aclname ?><li><a href="<?cs var:href ?>" <?cs 
        if $id == $trac.active_module ?>class="active"<?cs /if ?> 
        <?cs if:$accesskey!="" ?> accesskey="<?cs var:$accesskey ?>"<?cs 
        /if ?>><?cs var:text ?></a></li><?cs 
   /if ?><?cs 
/def ?>

<html>
  <head>
    <?cs if $project.name ?>
      <title><?cs var:project.name?><?cs if title 
                     ?>: <?cs var:title ?><?cs /if ?> - Trac</title>
    <?cs else ?>
      <title>Trac : <?cs var:title ?></title>
    <?cs /if ?>
    <style type="text/css">
      <!--
      @import url("<?cs var:$htdocs_location ?>/css/trac.css");
      @import url("<?cs var:$htdocs_location ?>/css/code.css");
      <?cs if:trac.active_module == 'browser' || trac.active_module == 'log' ?>
      @import url("<?cs var:$htdocs_location ?>/css/browser.css");
      <?cs elif:trac.active_module == 'timeline' ?>
      @import url("<?cs var:$htdocs_location ?>/css/timeline.css");
      <?cs elif:trac.active_module == 'changeset' || trac.active_module == 'wiki' ?>
      @import url("<?cs var:$htdocs_location ?>/css/changeset.css");
      <?cs elif:trac.active_module == 'newticket' || trac.active_module == 'ticket' ?>
      @import url("<?cs var:$htdocs_location ?>/css/ticket.css");
      <?cs elif:trac.active_module == 'report' ?>
      @import url("<?cs var:$htdocs_location ?>/css/report.css");
      <?cs elif:trac.active_module == 'search' ?>
      @import url("<?cs var:$htdocs_location ?>/css/search.css");
      <?cs /if ?>
      /* Dynamically/template-generated CSS below */
      #navbar { background: url("<?cs var:$htdocs_location ?>/topbar_gradient.png") top left #f7f7f7 }  
      #navbar a { background: url(<?cs var:$htdocs_location ?>/dots.gif) top left no-repeat; }
      #navbar a.active,#navbar a.active:visited { background: url("<?cs var:$htdocs_location ?>/topbar_active.png") top left repeat-x #d7d7d7;}  

       -->
    </style>
    <script src="<?cs var:$htdocs_location ?>/trac.js" type="text/javascript"></script>
</head>
<body>

<div id="header">
  <a id="hdrlogo" href="<?cs var:header_logo.link ?>"><img src="<?cs var:header_logo.src ?>" 
      width="<?cs var:header_logo.width ?>" 
      height="<?cs var:header_logo.height ?>" 
      alt="<?cs var:header_logo.alt ?>" /></a>
  <hr class="hide"/>
  <h2 class="hide">Navigation</h2>
  <div id="header-right">
   <form id="search" action="<?cs var:trac.href.search ?>" method="get">
    <div>
     <label for="proj-search">Search:</label>
     <input type="text" id="proj-search" name="q" size="10" value="" />
     <input type="submit" value="Search" />
     <input type="hidden" name="wiki" value="on" />
     <input type="hidden" name="changeset" value="on" />
     <input type="hidden" name="ticket" value="on" />
    </div>
   </form>
   <ul class="subheader-links">
    <li><?cs if $trac.authname == "anonymous" ?>
      <a href="<?cs var:trac.href.login ?>">Login</a>
    <?cs else ?> 
      logged in as <?cs var:trac.authname ?> </li>
      <li><a href="<?cs var:trac.href.logout ?>">Logout</a>
    <?cs /if ?></li>
    <li><a accesskey="6" href="<?cs var:trac.href.wiki ?>TracGuide">Help/Guide</a></li>
    <li style="display: none"><a accesskey="5" href="<?cs var:trac.href.wiki ?>TracFaq">FAQ</a></li>
    <li style="display: none"><a accesskey="0" href="<?cs var:trac.href.wiki ?>TracAccessibility">Accessibility</a></li>
    <li class="last"><a accesskey="9" href="<?cs var:trac.href.about ?>">About Trac</a></li>
   </ul>
  </div>
 </div>
  <div id="navbar">
    <ul>
      <?cs call:navlink("Wiki", $trac.href.wiki, "wiki", 
                        "WIKI_VIEW", "1") ?>
      <?cs call:navlink("Timeline", $trac.href.timeline, "timeline", 
                        "TIMELINE_VIEW", "2") ?>
      <?cs if $trac.active_module == "log" ?>	
    	<?cs set:$browser_view="log" ?>
      <?cs else  ?>	
    	<?cs set:$browser_view="browser" ?>
      <?cs /if  ?>	
      <?cs call:navlink("Browse Source", $trac.href.browser, $browser_view, 
                        "BROWSER_VIEW", "") ?>
      <?cs if $trac.active_module == "ticket" ?>	
    	<?cs set:$ticket_view="ticket" ?>
      <?cs else  ?>	
    	<?cs set:$ticket_view="report" ?>
      <?cs /if  ?>	
      <?cs call:navlink("View Tickets", $trac.href.report, $ticket_view, 
                        "REPORT_VIEW", "") ?>
      <a style="display: none" href="<?cs var:$trac.href.newticket ?>" accesskey="7"></a>
      <?cs call:navlink("New Ticket", $trac.href.newticket, "newticket", 
                        "TICKET_CREATE", "9") ?>
      <?cs call:navlink("Search", $trac.href.search, "search", 
                        "SEARCH_VIEW", "4") ?>
    </ul>
  </div>