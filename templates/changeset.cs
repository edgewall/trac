<?cs include "../templates/header.cs"?>

<h3>Change set <?cs var:changeset.revision ?></h3>

<table>
<tr>
<td align="right">revision:</td><td><?cs var:changeset.revision ?></td>
</tr>
<tr>
<td align="right">time:</td><td><?cs var:changeset.time ?></td>
</tr>
<tr>
<td align="right">author:</td><td><?cs var:changeset.author ?></td>
</tr>
<tr>
<td align="right">message:</td><td><?cs var:changeset.message ?></td>
</tr>
<tr>
<td align="right" valign="top">files:</td>
<td>

<table>

  <?cs each:item = changeset.changes ?>
    <tr>
      <?cs if item.change == "A" ?>
        <td><a href="<?cs var:item.log_href?>"><?cs var:item.name ?></a></td>
        <td>added</td>
      <?cs elif item.change == "M" ?>
        <td><a href="<?cs var:item.log_href?>"><?cs var:item.name ?></a></td>
        <td>modified</td>
      <?cs elif item.change == "D" ?>
        <td><?cs var:item.name ?></td><td>deleted</td>
      <?cs /if ?>
    </tr>
  <?cs /each ?>

</table>

</td>
</tr>
</table>

<h3>diffs</h3>
