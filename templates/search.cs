<?cs include "header.cs"?>
<div id="page-content">
 <div id="subheader-links">
 </div>
 <div id="main">
  <div id="main-content">

<h3>Search</h3>
<form action="<?cs var:trac.href.search ?>" method="get">
<div>
<input type="text" name="q" size="40" value="<?cs var:search.q ?>" />
<input type="submit" value="Search" /><br />
<input type="checkbox" <?cs if search.wiki ?>checked="checked"<?cs /if ?> name="wiki" />Wiki
<input type="checkbox" <?cs if search.ticket ?>checked="checked"<?cs /if ?> name="ticket" />Tickets
<input type="checkbox"  <?cs if search.changeset ?>checked="checked"<?cs /if ?> name="changeset" />Changesets
</div>
</form>

<?cs def result(title, body, link) ?>
 <div class="result-item">
 <a class="result-title" href="<?cs var:$link ?>"><?cs var:$title ?></a>
 <div class="result-body"><?cs var:$body ?></div>
 <span class="result-author">By <?cs var:$item.author ?></span>
 -  <span class="result-date"><?cs var:$item.datetime ?></span>
 </div>
<?cs /def ?>

<?cs if ? search.result.0.type ?>
 <h2>Search results
    <?cs if $search.result.page ?>
    (<?cs var $search.result.page * $search.results_per_page ?>-<?cs
          var ((1+$search.result.page) * $search.results_per_page)-1 ?>)
    <?cs /if ?>
</h2>
  <div id="search-result">
  <div id="searchable">

   <?cs each item=search.result ?> 
    <?cs if item.type == 1 ?>
     <?cs call result('['+item.data+']: '+item.shortmsg,
                      item.message,
                      item.changeset_href) ?>
    <?cs elif item.type == 2 ?>
     <?cs call result('#'+item.data+': '+item.title,
                      item.message,
                      item.ticket_href) ?>
    <?cs elif item.type == 3 ?>
     <?cs call result(item.data+': '+item.shortmsg,
                      item.message,
                      item.wiki_href) ?>
    <?cs /if ?>
   <?cs /each ?>
   </div>
    <?cs set:url=$trac.href.search+'?q='+url_escape($search.q) ?>
    <?cs if $search.wiki ?><?cs set:url=$url+'&wiki=on' ?><?cs /if 
      ?><?cs if $search.ticket ?><?cs set:url=$url+'&ticket=on' ?><?cs /if 
      ?><?cs if $search.changeset ?><?cs set:url=$url+'&changeset=on'
      ?><?cs /if ?>
    <?cs set:url=$url+'&page=' ?>
 
    <hr />
    <?cs if $search.result.page ?>
      <a href="<?cs var:$url ?><?cs var:$search.result.page-#1 ?>">Prev
Page</a>
    <?cs if $search.result.more ?>&nbsp;|&nbsp;<?cs /if ?>
    <?cs /if ?>
    <?cs if $search.result.more ?>
     <a href="<?cs var:$url ?><?cs var:$search.result.page+#1 ?>">Next Page</a>
    <?cs /if ?>
  
  </div>
<?cs else ?>
<div id="search-notfound">No results found.</div>
<?cs /if ?>
 </div> 
</div>
</div>
<?cs include "footer.cs"?>

