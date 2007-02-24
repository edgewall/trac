<?cs if:len(chrome.links.alternate) ?>
<div id="altlinks"><h3>Download in other formats:</h3><ul><?cs
 each:link = chrome.links.alternate ?><?cs
  set:isfirst = name(link) == 0 ?><?cs
  set:islast = name(link) == len(chrome.links.alternate) - 1?><li<?cs
    if:isfirst || islast ?> class="<?cs
     if:isfirst ?>first<?cs /if ?><?cs
     if:isfirst && islast ?> <?cs /if ?><?cs
     if:islast ?>last<?cs /if ?>"<?cs
    /if ?>><a rel="nofollow" href="<?cs var:link.href ?>"<?cs if:link.class ?> class="<?cs
    var:link.class ?>"<?cs /if ?>><?cs var:link.title ?></a></li><?cs
 /each ?></ul></div><?cs
/if ?>

</div>

<div id="footer">
 <hr />
 <a id="tracpowered" href="http://trac.edgewall.org/"><img src="<?cs
   var:htdocs_location ?>trac_logo_mini.png" height="30" width="107"
   alt="Trac Powered"/></a>
 <p class="left">
  Powered by <a href="<?cs var:trac.href.about ?>"><strong>Trac <?cs
  var:trac.version ?></strong></a><br />
  By <a href="http://www.edgewall.org/">Edgewall Software</a>.
 </p>
 <p class="right">
  <?cs var:project.footer ?>
 </p>
</div>

<?cs include "site_footer.cs" ?>
 </body>
</html>
