<script type="text/javascript">searchHighlight()</script>

<?cs if:len(links.alternate) ?>
<div id="altlinks">
 <h3>Download in other formats:</h3>
 <ul><?cs each:link = links.alternate ?>
  <li<?cs if:name(link) == len(links.alternate) - #1 ?> class="last"<?cs /if ?>>
   <a href="<?cs var:link.href ?>"<?cs if:link.class ?> class="<?cs
    var:link.class ?>"<?cs /if ?>><?cs var:link.title ?></a>
  </li><?cs /each ?>
 </ul>
</div>
<?cs /if ?>

</div>

<div id="footer">
 <hr />
 <a id="tracpowered" href="http://trac.edgewall.com/"><img src="<?cs
     var:$htdocs_location ?>trac_logo_mini.png" height="30" width="107"
     alt="Trac Powered"/></a>
 <p class="left">
  Powered by <a href="<?cs var:trac.href.about ?>"><strong>Trac <?cs
var:trac.version ?></strong></a><br />
  By <a href="http://www.edgewall.com/">Edgewall Software</a>.
 </p>
 <p class="right">
  <?cs var $project.footer ?>
 </p>
</div>

<?cs include "site_footer.cs" ?>
 </body>
</html>
