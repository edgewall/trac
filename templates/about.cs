<?cs include "header.cs"?>

<?cs if about.page == "config"?>

  <h3>Configuration</h3>
  <table>
  <tr>
  <th>Section</th><th>Name</th><th>Value</th>
  </tr>
  <?cs each:item = about.config ?>
    <tr>
      <td><?cs var:item.section ?></td>
      <td><?cs var:item.name ?></td>
      <td><?cs var:item.value ?></td>
    </tr>
  <?cs /each ?>
  </table>

<?cs else ?>

  <h3>About Trac</h3>
  <p>
   Version: <?cs var:trac.version ?>
  </p>
  <p>
  Trac is a minimalistic but highly useful software project environment based 
  around <a href="http://www.c2.com/cgi/wiki">Wiki concepts</a>. It extends 
  <a href="http://www.c2.com/cgi/wiki">Wiki concepts</a> by integrating an 
  interface to source revision control, bug/issue tracking database and 
  convenient report facilities.
  </p>
  <p>
  Trac is implemented as a set of Python modules and a CGI script.
  </p>
  <p>
  Relevant links:
  </p>
  <ul>
  <li><a href="http://projects.edgewall.com/trac/">Trac Project Website</a></li>
  <li><a href="http://www.edgewall.com/">Edgewall Research &amp; Development</a></li>
</ul>
<?cs /if ?>

<?cs include "footer.cs"?>
