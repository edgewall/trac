<?cs include "header.cs" ?>
<script src="<?cs var:htdocs_location ?>/trac.js" type="text/javascript"> 
</script>
<div id="page-content">
<div id="subheader-links">
  <a href="<?cs var:$trac.href.wiki ?>">Start Page</a>&nbsp;|
  <a href="<?cs var:$trac.href.wiki ?>TitleIndex">Title Index</a>&nbsp;|
  <a href="javascript:view_history()">Show/Hide History</a>
</div>
<hr class="hide"/>
<?cs if $wiki.history ?>
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
    <hr class="hide"/>
  <?cs /if ?>
  <div id="main">
    <div id="main-content">
      <div id="wiki-body">
        <?cs if $wiki.title_index.0.title ?>
          <h2>TitleIndex</h2>
          <?cs each item = $wiki.title_index ?>
            <li><a href="<?cs var:item.href?>"><?cs var:item.title ?></a></li>
          <?cs /each ?>
        <?cs else ?>
          <?cs if wiki.action == "edit" || wiki.action == "preview" ?>
            <h3>Edit "<?cs var:wiki.page_name ?>"</h3>
            <form action="<?cs var:wiki.current_href ?>" method="post">
              <p>
                <textarea name="text" rows="20" cols="80" style="width:100%"><?cs var:wiki.page_source ?></textarea>
              </p>
              <div id="wiki-formatting-help">
              Read <a href="<?cs var:$trac.href.wiki ?>WikiFormatting">WikiFormatting</a> for more information about available commands.
              </div>
              <p>
                <input type="submit" name="save" value="save changes" />&nbsp;
                <input type="submit" name="preview" value="preview" />&nbsp;
                <input type="submit" name="view" value="cancel" />
              </p>
            </form>
          <?cs /if ?>
          <?cs if wiki.action == "view" || wiki.action == "preview" ?>
            <div class="wikipage">
                <?cs var:wiki.page_html ?>
            </div>
            <?cs if wiki.action == "view" && trac.acl.WIKI_MODIFY ?>
              <p>
              <a id="wiki-edit-page" href="<?cs var:wiki_current_href?>?edit=yes">edit this page.</a>
              </p>
            <?cs /if ?>
          <?cs /if ?>
        <?cs /if ?>
      </div>
    </div>
    <div id="main-sidebar">
    </div>
  </div>
</div>
<?cs include: "footer.cs" ?>
