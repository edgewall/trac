<?cs include "header.cs"?>

<div id="ctxtnav" class="nav"></div>

<div id="content" class="changeset">
 <div id="title">
    <h1>Select Base and Target for Diff:</h1>
 </div>

 <div id="anydiff">
  <form action="<?cs var:anydiff.changeset_href ?>" method="get">
   <table>
    <tr>
     <th><label for="old_path">From:</label></th>
     <td>
      <input type="text" id="old_path" name="old_path" value="<?cs
         var:anydiff.old_path ?>" size="44" />
      <label for="old_rev">at Revision:</label>
      <input type="text" id="old_rev" name="old" value="<?cs
         var:anydiff.old_rev ?>" size="4" />
     </td>
    </tr>
    <tr>
     <th><label for="new_path">To:</label></th>
     <td>
      <input type="text" id="new_path" name="new_path" value="<?cs
         var:anydiff.new_path ?>" size="44" />
      <label for="new_rev">at Revision:</label>
      <input type="text" id="new_rev" name="new" value="<?cs
         var:anydiff.new_rev ?>" size="4" />
     </td>
    </tr>
   </table>
   <div class="buttons">
      <input type="submit" value="View changes" />
   </div>
  </form>
 </div>
 <div id="help">
  <strong>Note:</strong> See <a href="<?cs var:trac.href.wiki
  ?>/TracChangeset#ExaminingDifferencesBetweenBranches">TracChangeset</a> for help on using the arbitrary diff feature.
 </div>
</div>

<?cs include "footer.cs"?>
