<?cs include "header.cs"?>

<div id="ctxtnav" class="nav"></div>

<div id="content" class="error">

 <?cs if error.type == "TracError" ?>
  <h1><?cs var:error.title ?></h1>
  <p class="message"><?cs var:error.message ?></p>

 <?cs elif error.type == "internal" ?>
  <h1>Oops&hellip;</h1>
  <div class="message">
   <strong>Trac detected an internal error:</strong>
   <pre><?cs var:error.message ?></pre>
  </div>
  <p>If you think this really should work and you can reproduce it, you  should
   consider reporting this problem to the Trac team.</p>
  <p>Go to <a href="<?cs var:trac.href.homepage ?>"><?cs
   var:trac.href.homepage ?></a> and create a new ticket where you describe
   the problem, how to reproduce it. Don't forget to include the Python
   traceback found below.</p>

 <?cs /if ?>

 <p>
  <a href="<?cs var:trac.href.wiki ?>/TracGuide">TracGuide</a>
  &mdash; The Trac User and Administration Guide
 </p>
 <?cs if:error.traceback ?>
  <h4>Python Traceback</h4>
  <pre><?cs var:error.traceback ?></pre>
 <?cs /if ?>

</div>
<?cs include "footer.cs"?>
