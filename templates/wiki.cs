<?cs include: "header.cs" ?>
<div id="subheader-links">
<a href="<?cs var:$trac.href.wiki ?>">Start Page</a> | 
<a href="<?cs var:$trac.href.wiki ?>TitleIndex">Title Index</a>
</div>

<hr />

<div id="main">
 <?cs if $wiki.title_index.0.title ?>
   <h2>TitleIndex</h2>
   <?cs each item = $wiki.title_index ?>
     <li><a href="<?cs var:item.href?>"><?cs var:item.title ?></a></li>
   <?cs /each ?>
 <?cs else ?>
   <?cs var:content ?>
 <?cs /if ?>
</div>

<script type="text/javascript" src="<?cs var:htdocs_location ?>trac.js">
</script>
 <?cs if $wiki.history.0 == '0' ?>
 <table id="wiki-history">
  <tr>
   <th>Version</th>
   <th>Time</th>
   <th>Author</th>
   <th>IP#</th>
  </tr>
  <?cs each item = $wiki.history ?>
    <tr>
      <td><a href="<?cs var:$item.url ?>"><?cs var:$item.version ?></a></td>
      <td><?cs var:$item.time ?></td>
      <td><?cs var:$item.author ?></td>
      <td><?cs var:$item.ipnr ?></td>
    </tr>
  <?cs /each ?>
 </table>
<?cs /if ?>


<?cs include: "footer.cs" ?>
