<?cs set:html.stylesheet = 'css/report.css' ?>
<?cs include:"header.cs" ?>
<?cs include:"macros.cs" ?>

<div id="ctxtnav" class="nav">
</div>

<div id="content" class="query">
 <h1><?cs var:title ?></h1>

<?cs if:len(query.results) ?>
 <p><?cs var:len(query.results) ?> tickets matched this query.</p>
 <table id="tktlist" class="listing">
  <thead><tr><?cs each:header = query.headers ?><?cs
   if:name(header) == 0 ?><th class="ticket">
    <?cs if:header.ordered ?><strong><?cs /if ?>
    <a href="<?cs var:header.href ?>">Ticket</a>
    <?cs if:header.ordered ?></strong><?cs /if ?></th><?cs
   else ?>
    <th><?cs if:header.ordered ?><strong><?cs /if ?>
     <a href="<?cs var:header.href ?>"><?cs var:header.name ?></a>
    <?cs if:header.ordered ?></strong><?cs /if ?></th><?cs
   /if ?>
  <?cs /each ?></tr></thead>
  <tbody>
   <?cs each:result = query.results ?><tr class="<?cs
     if:name(result) % 2 ?>odd<?cs else ?>even<?cs /if ?> <?cs
     var:result.priority ?>">
    <?cs each:header = query.headers ?><?cs
     if:name(header) == 0 ?>
      <td class="ticket"><a href="<?cs var:result.href ?>"><?cs
        var:result.id ?></a></td><?cs
     else ?>
      <td><?cs call:get(result, header.name) ?></td><?cs
     /if ?>
    <?cs /each ?>
   </tr><?cs /each ?>
  </tbody>
 </table>
<?cs else ?>
 <p>No tickets matched this query.</p>
<?cs /if ?>

 <div id="help">
  <strong>Note:</strong> See <a href="<?cs var:$trac.href.wiki ?>/TracQuery">TracQuery</a> 
  for help on using queries.
 </div>

</div>
<?cs include:"footer.cs" ?>
