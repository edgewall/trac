<?cs include "header.cs"?>
<div id="page-content">
<div id="subheader-links">
   <a href="<?cs var:trac.href.about ?>">About Trac</a>&nbsp;
   | <a href="<?cs var:trac.href.about_config ?>">View Config</a>&nbsp;
</div>
 <div id="main">
  <div id="main-content">

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
  <a class="noline" href="http://trac.edgewall.com"
      style="float: right"><img src="<?cs var:htdocs_location ?>trac_banner.png" alt=""/></a>

<h1>About Trac</h1>
  <p>This website is using Trac version <?cs var:trac.version ?></p>
  <p>
  Trac is a minimalistic but useful software bug tracking system and project
  environment based around issue tracking and <a href="http://www.c2.com/cgi/wiki">wiki concepts</a>.
  </p>
  <p>
  It brings <a href="<?cs var:trac.href.wiki ?>">wiki text</a>, an interface to 
source code  <a href="<?cs var:trac.href.browser ?>">revision control</a>,
a flexible <a href="<?cs var:trac.href.timeline ?>">bug/issue tracking database</a> and 
  convenient <a href="<?cs var:trac.href.report ?>">report facilities</a>
together as an integrated environment.
  </p>

  <p>
  Trac is a product of <a href="http:/www.edgewall.com/">Edgewall Research
  &amp; Development</a>, provider of professional Linux and software
  development services.
  </p>
  
  <h2>The Trac Project</h2>
  <p>
  Trac is implemented as a set of Python modules and a CGI script and
  distributed under the GNU General Public License (GPL).
  </p>
  <p>
  Please visit the Trac open source project at: <br />
    <a href="http://projects.edgewall.com/trac/">http://projects.edgewall.com/trac/</a>
  </p>
  <h2>Links:</h2>
    <ul>
    <li><a href="http://trac.edgewall.com/">Trac Product Information</a></li>
    <li><a href="http://www.edgewall.com/">Edgewall Website</a></li>
  </ul>
  <a class="noline" href="http://www.edgewall.com/">
   <img style="display: block; margin: 30px" src="<?cs var:htdocs_location ?>edgewall_logo_left-226x43.png"
     alt="Edgewall Research  &amp; Development"/></a>
<?cs /if ?>


 </div>
</div>
</div>
<?cs include "footer.cs"?>
