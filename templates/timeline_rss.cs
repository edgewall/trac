<?xml version="1.0"?>
<rss version="2.0"><?cs
 def:rss_item(category,title, link, descr) ?>
  <item><?cs
   if:item.author.email ?>
    <author><?cs var:item.author.email ?></author><?cs
   /if ?>
   <pubDate><?cs var:item.datetime ?></pubDate>
   <title><?cs var:title ?></title>
   <link><?cs var:link ?></link>
   <description><?cs var:descr ?></description>
   <category><?cs var:category ?></category>
  </item><?cs 
 /def ?>

 <channel><?cs
  if:project.name.encoded ?>
   <title><?cs var:project.name.encoded ?>: <?cs var:title ?></title><?cs
  else ?>
   <title><?cs var:title ?></title><?cs
  /if ?>
  <link><?cs var:base_host ?><?cs var:trac.href.timeline ?></link>
  <description>Trac Timeline</description>
  <language>en-us</language>
  <generator>Trac v<?cs var:trac.version ?></generator>
  <image>
   <title><?cs var:project.name.encoded ?></title>
   <url><?cs if:!header_logo.src_abs ?><?cs var:base_host ?><?cs /if ?><?cs
    var:header_logo.src ?></url>
   <link><?cs var:base_host ?><?cs var:trac.href.timeline ?></link>
  </image><?cs
  each:item = timeline.items ?><?cs
   if:item.type == 'changeset' ?><?cs
    call:rss_item('Changeset', 'Changeset [' + item.idata + '] by ' + item.author,
                  item.href, item.message) ?><?cs
   elif:item.type == 'newticket' ?><?cs
    call:rss_item('Ticket', 'Ticket #' + item.idata + ' created by ' + item.author,
                  item.href, item.message) ?><?cs
   elif:item.type == 'closedticket' ?><?cs
    call:rss_item('Ticket', 'Ticket #' + item.idata + ' resolved as ' + item.tdata + ' by ' + item.author, item.href, item.message) ?><?cs
   elif:item.type == 'reopenedticket' ?><?cs
    call:rss_item('Ticket', '#' + item.idata + ' reopened by ' + item.author,
                  item.href, item.message) ?><?cs
   elif:item.type == 'wiki' ?><?cs
    call:rss_item('Wiki', item.tdata + ' page edited by ' + item.author,
                  item.href, item.message) ?><?cs
   elif:item.type == 'milestone' ?><?cs
    call:rss_item('Milestone', 'Milestone ' + item.tdata + ' reached',
                  item.href, 'Milestone ' + item.tdata + ' reached.') ?><?cs
   /if ?><?cs
  /each ?>
 </channel>
</rss>
