<?cs include "header.cs"?>

<?cs if error.type == "TracError" ?>

<h3><?cs var:error.title ?></h3>

<div class="error">
<?cs var:error.message ?>
</div>

<?cs elif error.type == "internal" ?>

<h3>Oops...</h3>

<div class="error">
Trac detected an internal error:
<pre>
<?cs var:error.message ?>
</pre>
</div>

<p>
If you think this really should work and you can reproduce it. Then you 
should consider to report this problem to the Trac team.
</p>
<p>
Go to
<a href="<?cs var:trac.href.homepage ?>"><?cs var:trac.href.homepage ?></a> 
and create a new ticket where you describe
the problem, how to reproduce it and don't forget to include the python
traceback found below.
</p>

<?cs elif error.type == "permission" ?>

<h3>Permission Denied</h3>

<div class="error">
This action requires <tt><?cs var:error.action ?></tt> permission.
</div>

<p>
<b>Note</b>: See
<a href="<?cs var:trac.href.wiki ?>/TracPermissions">TracPermissions</a>
for help on managing Trac permissions.
</p>

<?cs /if ?>

<p>
<a href="<?cs var:trac.href.wiki ?>/TracGuide">TracGuide</a>
-- The Trac User and Administration Guide
</p>

<?cs if $error.traceback ?>
<h4>Python traceback</h4>
<pre>
<?cs var:error.traceback ?>
</pre>
<?cs /if ?>

<?cs include "footer.cs"?>
