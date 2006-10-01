<?xml version="1.0"?>
<rss version="2.0">
 <channel><?cs
  if:project.name_encoded ?>
   <title><?cs var:project.name_encoded ?>: Ticket Query</title><?cs
  else ?>
   <title>Ticket Query</title><?cs
  /if ?>
  <link><?cs var:query.href ?></link><?cs
  if:project.descr ?>
   <description><?cs var:project.descr ?></description><?cs
  /if ?>
  <language>en-us</language>
  <generator>Trac v<?cs var:trac.version ?></generator><?cs
  if:chrome.logo.src ?>
   <image>
    <title><?cs var:project.name_encoded ?></title>
    <url><?cs if:!chrome.logo.src_abs ?><?cs var:base_host ?><?cs /if ?><?cs
     var:chrome.logo.src ?></url>
    <link><?cs var:query.href ?></link>
   </image><?cs
  /if ?><?cs
  each:result = query.results ?>
   <item>
    <link><?cs var:result.href ?></link>
    <guid isPermaLink="false"><?cs var:result.href ?></guid>
    <title><?cs var:'#' + result.id + ': ' + result.summary ?></title><?cs
    if:result.created ?>
     <pubDate><?cs var:result.created ?></pubDate><?cs
    /if ?><?cs
    if:result.reporter ?>
     <author><?cs var:result.reporter ?></author><?cs
    /if ?>
    <description><?cs var:result.description ?></description>
    <category>Tickets</category>
    <comments><?cs var:result.href ?>#changelog</comments>
   </item><?cs
  /each ?>
 </channel>
</rss>
