<?cs include "header.cs"?>

<?cs if error.type == "internal" ?>

<h3>Oups...</h3>

<p>
Trac detected an internal error:
</p>
<pre>
<?cs var:error.message ?>
</pre>

<p>
If you think this really should work and you can reproduce it. Then you 
should consider to report this problem to the Trac team.
</p>
<p>
Go to
<a href="<?cs var:trac.href.homepage ?>"><?cs var:trac.href.homepage ?></a> 
and there you create a new ticket where you describe
the problem, how to reproduce it and don't forget to include the python
traceback found below.
</p>

<?cs elif error.type == "permission" ?>

<h3>Permission denied</h3>
<p>
This action requires <tt><?cs var:error.action ?></tt> permission.
</p>

<p>
The Trac administration program <tt>trac_admin.py</tt> can be used to grant 
permissions to users like this:

<pre>
  $ trac_admin.py /path/to/trac.db permission add <?cs var:trac.authname ?> <?cs var:error.action ?>
</pre>
or to all unauthenticated users:
<pre>
  $ trac_admin.py /path/to/trac.db permission add anonymous <?cs var:error.action ?>
</pre>
</p>

<?cs /if ?>

<?cs if $error.traceback ?>
<h4>Python traceback</h4>
<pre>
<?cs var:error.traceback ?>
</pre>
<?cs /if ?>

<?cs include "footer.cs"?>
