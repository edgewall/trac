<?cs include "../templates/header.cs" ?>

<h3>New ticket:</h3>

<form action="<?cs var:cgi_name ?>" method="POST">
<input type="hidden" name="mode" value="ticket">
<input type="hidden" name="action" value="create">
<input type="hidden" name="status" value="new">
<table>
<tr>
<td align="right">reporter:</td><td><input type="text" name="reporter" value="<?cs var:newticket.reporter ?>"></td>
<td align="right">priority:</td>
<td><?cs var:newticket.priority_select ?></td>
</tr>
<tr>
<td align="right">component:</td>
<td><?cs var:newticket.component_select ?></td>
<td align="right">milestone:</td>
<td<?cs var:newticket.milestone_select ?></td>
</tr>
<tr>
<td align="right">version:</td>
<td><?cs var:newticket.version_select ?></td>
<td align="right">assign to:</td>
<td><input type="text" name="owner"></td>
</tr>
<tr>
<td align="right">severity:</td><td><?cs var:newticket.severity_select ?></td>
</tr>
<tr>
<td align="right">cc:</td>
<td><input type="text" name="cc" size="50"></td>
</tr>
<tr>
<td align="right">url:</td>
<td><input type="text" name="url" size="50"></td>
</tr>
<tr>
<td align="right">summary:</td>
<td colspan="3"><input type="text" name="summary" size="50"></td>
</tr>
<tr>
<td align="right">description:</td>
	<td colspan="3">
	<textarea name="description" rows="8" cols="70"></textarea>
	</td>
</tr>
<tr>
<td align="right" colspan="4">
<input type="submit" value="commit">&nbsp;
<input type="reset" value="reset"></td>
</tr>
</table>
</form>

<?cs include "../templates/footer.cs" ?>
