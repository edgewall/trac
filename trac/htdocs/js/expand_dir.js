// Enable expanding/folding folders in TracBrowser

var counter = 0;

// enableExpandDir expect a `rows` jQuery object matching rows that will
// acquire the capability to be expanded and folded. 
// Those rows correspond to the entries of the parent folder whose 
// row has an id of `parentid`.

function enableExpandDir(parentid, rows) {
  var entries = [];
  rows.each(function () {
    var folderid = "f" + counter++;
    entries.push("#"+folderid);
    this.id = folderid;
  }).find("span.direxpand").css("cursor", "pointer").click(toggleDir);
  
  var parent = document.getElementById(parentid);
  if ( parent )
    parent._entries = entries;
}

function toggleDir() {
  var td = $(this).parent();
  if ( $(this).attr("class") == "direxpand" ) {
    $(this).attr("class", "dirfold").attr("title", "Fold directory");
    expandDir(td);
  } else {
    $(this).attr("class", "direxpand").attr("title", "Expand directory");
    foldDir(td.parent());
  }
}

function expandDir(td) {
  var tr = td.parent();
  var folderid = tr.get(0).id;

  if (tr.get(0)._entries) { // then simply re-expand collapsed folder
    tr.siblings("tr."+folderid).show();
    // as the above shows all, take care to fold again what was already folded
    restoreEntries(tr);
    return;
  }

  var a = td.children("a");
  var href = a.attr("href");
  var depth = parseFloat(td.css("padding-left").replace(/^(\d*\.\d*).*$/, 
							"$1")) + 20;
  // insert "Loading ..." row
  tr.after('<tr><td class="name" colspan="5" style="padding-left: ' +
	   depth + 'px"><span class="loading">Loading ' + a.text() +
	   '...</span></td></tr>');

  // prepare the class that will be used by foldDir to identify all the 
  // rows to be removed when collapsing that folder
  td.addClass("expanded");
  tr.attr("id", folderid).addClass(folderid);
  var ancestor_folderids = $.grep(tr.attr("class").split(" "), 
				  function(c) { return c.match(/^f\d+$/)});
  ancestor_folderids.push(folderid);

  $.get(href, {action: "inplace"}, function(data) {
    // remove "Loading ..." row
    tr.next().remove();
    // insert folder content rows
    var rows = $(data.replace(/^<!DOCTYPE[^>]+>/, "")).filter("tr");
    rows.addClass(ancestor_folderids.join(" "));
    rows.children("td.name").css("padding-left", depth);
    enableExpandDir(folderid, rows);
    tr.after(rows);
  });
}

function foldDir(tr) {
  var folderid = tr.get(0).id;
  tr.siblings("tr."+folderid).hide();
}

function restoreEntries(tr) {
  var entries = tr.get(0)._entries;
  if (entries)
  $.each(entries, function (i, entry) {
    var entry_tr = $(entry);
    if (entry_tr.find("span.direxpand").length)
      foldDir(entry_tr);
    else
      restoreEntries(entry_tr);
  });
}
