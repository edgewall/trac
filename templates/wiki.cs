<?cs include: "header.cs" ?>

<script language="JavaScript" src="<?cs var:htdocs_location ?>trac.js">
</script>

<?cs if $wiki.title_index.0.title ?>

  <h2>TitleIndex</h2>

  <?cs each item = $wiki.title_index ?>
    <li><a href="<?cs var:item.href?>"><?cs var:item.title ?></a></li>
  <?cs /each ?>

<?cs else ?>
  <p>
    <?cs var:content ?>
  </p>
<?cs /if ?>

<?cs include: "footer.cs" ?>
