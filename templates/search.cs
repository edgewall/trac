<?cs include "header.cs"?>
<script type="text/javascript">
addEvent(window, 'load', function() { document.getElementById('q').focus()}); 
</script>
<div id="page-content">
 <div id="subheader-links">
 </div>
 <div id="main">
  <div id="main-content">

<form action="<?cs var:trac.href.search ?>" method="get">
<div>
<h3 id="search-hdr"><label for="q">Search</label></h3>
<input type="text" id="q" name="q" size="40" value="<?cs var:search.q ?>" />
<input type="submit" value="Search" /><br />
<input type="checkbox" <?cs if search.wiki ?>checked="checked"<?cs /if ?> 
       id="wiki" name="wiki" />
<label for="wiki">Wiki</label>
<input type="checkbox" <?cs if search.ticket ?>checked="checked"<?cs /if ?>
       id="ticket" name="ticket" />
<label for="ticket">Tickets</label>
<input type="checkbox"  <?cs if search.changeset ?>checked="checked"<?cs /if ?>
       id="changeset" name="changeset" />
<label for="changeset">Changesets</label>
</div>
</form>

<?cs def result(title, keywords, body, link) ?>
 <div class="result-item">
 <a class="result-title" href="<?cs var:$link ?>"><?cs var:$title ?></a>
 <?cs if:$keywords ?><div class="result-keywords"><?cs var:$keywords ?></div><?cs /if ?>
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
                      item.keywords,
                      item.message,
                      item.changeset_href) ?>
    <?cs elif item.type == 2 ?>
     <?cs call result('#'+item.data+': '+item.title,
                      item.keywords,
                      item.message,
                      item.ticket_href) ?>
    <?cs elif item.type == 3 ?>
     <?cs call result(item.data+': '+item.shortmsg,
                      item.keywords,
                      item.message,
                      item.wiki_href) ?>
    <?cs /if ?>
   <?cs /each ?>
   </div>
    <?cs set:url=$trac.href.search+'?q='+ $search.q ?>
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
<?cs elif $search.q ?>
 <div id="search-notfound">No matches found.</div>
<?cs /if ?>
 </div> 

 <div id="help" style="text-align: left; margin-top: 2em">
  <strong>Note:</strong> See <a href="<?cs var:$trac.href.wiki ?>TracSearch">TracSearch</a>  for help on searching.
 </div>


</div>
</div>
<?cs include "footer.cs"?>

