<?cs include "header.cs"?>

<h3>Search</h3>
<form action="<?cs var:cgi_location ?>" method="GET">
<input type="hidden" name="mode" value="search">
<input type="text" name="q" size="40" value="<?cs var:search.q ?>">
<input type="submit" value="Search">
<br>
<input type="checkbox" <?cs var:search.ticket ?> name="ticket">Tickets
<input type="checkbox"  <?cs var:search.changeset ?> name="changeset">Changesets
</form>

<?cs if ? search.result.0.type ?>
  <br><br>
  <?cs set:idx = #0 ?>

  <table class="listing">
    <tr>
      <th class="header-left">Results</th>
    </tr>
    <?cs each item=search.result ?>
      <?cs if idx % #2 ?>
        <tr class="item-row-even">
      <?cs else ?>
        <tr class="item-row-odd">
      <?cs /if ?>
      <?cs if item.type == 1 ?>
      <td>
	Changeset [<a href="<?cs var:item.changeset_href ?>"><?cs var:item.data ?></a>] by <?cs var:item.author ?>: <?cs var:item.message ?>
      </td>
      <?cs elif item.type == 2 ?>
      <td>
	Ticket <a href="<?cs var:item.ticket_href ?>">#<?cs var:item.data ?></a> by <?cs var:item.author ?>: <?cs var:item.message ?>
      </td>
      <?cs elif item.type == 3 ?>
      <td>
	Wiki page <a href="<?cs var:item.wiki_href ?>"><?cs var:item.data ?></a> by <?cs var:item.author ?>
      </td>
      <?cs /if ?>
    </tr>
    <?cs set:idx = idx + #1 ?>
    <?cs /each ?>
  </table>

<?cs /if ?>
<br>
Note: only the first 20 results are shown.

<?cs include "footer.cs"?>

