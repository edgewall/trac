<?cs include "header.cs" ?>
<?cs include "macros.cs" ?>
<div id="page-content">
<h2 class="hide">Wiki Navigation</h2>
<ul class="subheader-links">
  <li><a href="<?cs var:$trac.href.wiki ?>">Start Page</a></li>
  <li><a href="<?cs var:$trac.href.wiki ?>/TitleIndex">Title Index</a></li>
  <li><a href="<?cs var:$trac.href.wiki ?>/RecentChanges">Recent Changes</a></li>
  <?cs if $wiki.history ?>
    <li class="last"><a href="javascript:view_history()">Show/Hide History</a></li>
  <?cs else ?>
    <li class="last">Show/Hide History</li>
  <?cs /if ?>
</ul>

<?cs def:day_separator(date) ?>
  <?cs if: $date != $current_date ?>
    <?cs set: $current_date = $date ?>
    </ul>
    <h3 class="recentchanges-daysep"><?cs var:date ?>:</h3>
    <ul>
  <?cs /if ?>
<?cs /def ?>

<hr class="hide"/>
<?cs if $wiki.history ?>
    <h3 class="hide">Page History</h3>
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
             href="<?cs var:$item.url ?>"><?cs var:$item.version ?></a>&nbsp;(<a class="wiki-history-link"
                  href="<?cs var:$item.diff_url ?>">diff</a>)</td>
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
          <ul>
          <?cs each item = $wiki.title_index ?>
            <li><a href="<?cs var:item.href?>"><?cs var:item.title ?></a></li>
          <?cs /each ?>
          </ul>

        <?cs elif $wiki.recent_changes.0.title ?>
          <h2>RecentChanges</h2>
          <ul>
          <?cs each item = $wiki.recent_changes ?>
            <?cs call:day_separator(item.time) ?>
            <li><a href="<?cs var:item.href?>"><?cs var:item.title ?></a></li>
          <?cs /each ?>
          </ul>

        <?cs elif wiki.action == "diff" ?>
          <div class="hide">
            <hr class="hide" />
            <h2>-=&gt; Note: Diff viewing requires CSS2 &lt;=-</h2>
            <p>
              Output below might not be useful.
            </p>
            <hr class="hide" />
          </div>
          <div id="chg-diff">
            <div id="chg-legend">
              <h3>Legend</h3>
              <span class="diff-legend-add"> </span> Added <br />
              <span class="diff-legend-rem"> </span> Removed <br />
              <span class="diff-legend-mod"> </span> Modified <br />
              <span class="diff-legend-unmod"> </span> Unmodified <br />
            </div>
          </div>
          <div class="chg-diff-file">
           <?cs call:diff_display(wiki.diff) ?>
          </div>
        <?cs else ?>
          <?cs if wiki.action == "edit" || wiki.action == "preview" ?>
            <h3>Editing "<?cs var:wiki.page_name ?>"</h3>
            <form action="<?cs var:wiki.current_href ?>" method="post">
              <div>
                <input type="hidden" name="edit_version"
                     value="<?cs var:wiki.edit_version?>" />
                <label for="text">Page source:</label><br />
                <textarea id="text" name="text" rows="20" cols="80" style="width:100%"><?cs var:wiki.page_source ?></textarea>
              </div>
              <div id="help">
              <b>Note:</b> See <a href="<?cs var:$trac.href.wiki
?>/WikiFormatting">WikiFormatting</a> and <a href="<?cs var:$trac.href.wiki
?>/TracWiki">TracWiki</a> for help on editing wiki content.
              </div>
              <fieldset>
                <legend>Change information</legend>
                <div style="display: inline; float: left; margin: 0 .5em;">
                  <label for="author">Your email or username:</label><br />
                  <input id="author" type="text" name="author" size="30"
                       value="<?cs var:wiki.author?>"/>
                </div>
                <div>
                  <label for="comment">Comment about this change (optional):</label>
                  <br />
                  <input id="comment" type="text" name="comment" size="60"
                        value="<?cs var:wiki.comment?>" />
                </div>
                <div class="buttons">
                    <input type="submit" name="save" value="Save changes" />&nbsp;
                    <input type="submit" name="preview" value="Preview" />&nbsp;
                    <input type="submit" name="view" value="Cancel" />
                </div>
              </fieldset>
            </form>
          <?cs /if ?>
          <?cs if wiki.action == "view" || wiki.action == "preview" ?>
            <?cs if wiki.action == "preview" ?><hr /><?cs /if ?>
            <div class="wikipage">
                <div id="searchable">
                 <?cs var:wiki.page_html ?>
                </div>
            </div>
          <?cs if $wiki.attachments.0.name ?>
           <h3 id="tkt-changes-hdr">Attachments</h3>
           <ul class="tkt-chg-list">
           <?cs each:a = wiki.attachments ?>
             <li class="tkt-chg-change"><a href="<?cs var:a.href ?>">
             <?cs var:a.name ?></a> (<?cs var:a.size ?>) -
             <?cs var:a.descr ?>,
             added by <?cs var:a.author ?> on <?cs var:a.time ?>.</li>
           <?cs /each ?>
         </ul>
         <?cs /if ?>
         <?cs if wiki.action == "view" && trac.acl.WIKI_MODIFY ?>
           <form class="inline" method="get" action=""><div>
               <input type="hidden" name="edit" value="yes" />
               <input type="submit" value="Edit This Page" />
              </div></form>
              <form class="inline" method="get" action="<?cs
                     var:cgi_location?>/attachment/wiki/<?cs
                     var:wiki.name ?>"><div>
               <input type="submit" value="Attach File" />
              </div></form>
              <div class="tiny" style="clear: both">&nbsp;</div>
            <?cs /if ?>
          <?cs /if ?>
        <?cs /if ?>
      </div>
    </div>
  </div>
</div>
<?cs include: "footer.cs" ?>
