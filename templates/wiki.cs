<?cs include: "header.cs" ?>
<script src="/trac_common/trac.js" type="text/javascript"> 
</script>

<div id="subheader-links">
<a href="<?cs var:$trac.href.wiki ?>">Start Page</a> |
<a href="<?cs var:$trac.href.wiki ?>TitleIndex">Title Index</a> |
<a href="javascript:view_history()">Show/Hide History</a>
</div>
<hr />
<?cs if $wiki.history.0 == '0' ?>
  <table id="wiki-history">
    <tr>
      <th>Version</th>
      <th>Time</th>
      <th>Author</th>
      <th>IP#</th>
    </tr>
    <?cs each item = $wiki.history ?>
      <tr class="wiki-history-row">
        <td><a class="wiki-history-link" 
           href="<?cs var:$item.url ?>"><?cs var:$item.version ?></a></td>
        <td><a class="wiki-history-link" 
             href="<?cs var:$item.url ?>"><?cs var:$item.time ?></a></td>
        <td><a class="wiki-history-link" 
             href="<?cs var:$item.url ?>"><?cs var:$item.author ?></a></td>
        <td><a class="wiki-history-link" 
             href="<?cs var:$item.url ?>"><?cs var:$item.ipnr ?></a></td>
      </tr>
    <?cs /each ?>
  </table>
  <hr />
<?cs /if ?>
<div id="main">
  <div id="main-content">
    <div id="wiki-body">
      <?cs if $wiki.title_index.0.title ?>
        <h2>TitleIndex</h2>
        <?cs each item = $wiki.title_index ?>
          <li>
            <a href="<?cs var:item.href?>"><?cs var:item.title ?></a>
          </li>
        <?cs /each ?>
      <?cs else ?>
        <?cs var:content ?>
      <?cs /if ?>
    </div>
  </div>
  <div id="main-sidebar">
  </div>
</div>

<?cs include: "footer.cs" ?>
