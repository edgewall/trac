<!DOCTYPE html
    PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head><title>Available Projects</title></head>
<body><h1>Available Projects</h1><ul><?cs
 each:project = projects ?><li><?cs
  if:project.href ?>
   <a href="<?cs var:project.href ?>" title="<?cs var:project.description ?>">
    <?cs var:project.name ?></a><?cs
  else ?>
   <small><?cs var:project.name ?>: <em>Error</em> <br />
   (<?cs var:project.description ?>)</small><?cs
  /if ?>
  </li><?cs
 /each ?></ul></body>
</html>
