<?cs include: "header.cs"?>

<h3>Revision <?cs var:revision?>: <?cs var:browser.path_links?></h3>

<form action="<?cs var:cgi_location ?>" method="get">
  <input type="hidden" name="mode" value="browser">
  <input type="hidden" name="path" value="<?cs var:browser.path?>">
  Change revision: 
  <input type="text" name="rev" value="<?cs var:browser.revision?>" size="6">
  <input type="submit" value="Change">
</form>
<br>

<table class="listing" cellspacing="0" cellpadding="0">

<tr class="listing-header">
  <th class="header-left">&nbsp;</th>
  <th class="header-left">name</th>
  <th class="header-right">size</th>
  <th class="header-right">rev</th>
  <th class="header-left">date</th>
</tr>

<?cs if $browser.path != "/" ?>
  <tr class="item-row-even">
    <td class="icon-column">
      <a href="<?cs var:browser.parent_href ?>">
        <img src="<?cs var:htdocs_location ?>/folder.png" 
	 width="16" height="16">
      </a>
   </td>
   <td class="name-column">
     <a href="<?cs var:browser.parent_href ?>">..</a>
   </td>
   <td class="size-column">&nbsp;</td>
   <td class="rev-column">&nbsp;</td>
   <td class="date-column">&nbsp;</td>
   </tr>
<?cs /if ?>

<?cs set:idx = #0 ?>
<?cs each:item = browser.items ?>

  <?cs if idx % #2 ?>
    <tr class="item-row-even">
  <?cs else ?>
    <tr class="item-row-odd">
  <?cs /if ?>

  <?cs if item.is_dir == #1 ?>
    <td class="icon-column">
      <a href="<?cs var:item.browser_href ?>">
      <img src="<?cs var:htdocs_location ?>/folder.png" width="16" height="16">
      </a>
    </td>
    <td class="name-column">
      <a href="<?cs var:item.browser_href ?>"><?cs var:item.name ?></a>
    </td>
  <?cs else ?>
    <td class="icon-column">
      <a href="<?cs var:item.log_href ?>">
      <img src="<?cs var:htdocs_location ?>/file.png" width="16" height="16">
      </a>
    </td>
    <td class="name-column">
      <a href="<?cs var:item.log_href ?>"><?cs var:item.name ?></a>
    </td>
  <?cs /if ?>

  <td class="size-column">
    <?cs if item.size != #0 ?><?cs var:item.size ?><?cs /if ?>
  </td>
  <td class="rev-column">
    <?cs if item.is_dir == #1 ?>
      <?cs var:item.created_rev ?>
    <?cs else ?>
      <a href="<?cs var:item.rev_href ?>"><?cs var:item.created_rev ?></a>
    <?cs /if ?>
  </td>
  <td class="date-column">
    <?cs var:item.date ?>
  </td>
  </tr>
<?cs set:idx = idx + #1 ?>
<?cs /each ?>

</table>

<?cs include:"footer.cs"?>
