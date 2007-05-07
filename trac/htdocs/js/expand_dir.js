// Enable expanding/folding folders in TracBrowser

var counter = 0;

// enableExpandDir adds the capability to folder rows to be expanded and folded
// It also teach the rows about their ancestors. It expects:
//  - `parent_tr`, the logical parent row
//  - a `rows` jQuery object matching the newly created entry rows

function enableExpandDir(parent_tr, rows) {
  var entries = [];
  var ancestor_folderids = [];
  // the ancestors folder ids are present in the parent_tr class attribute
  if (parent_tr)
    ancestor_folderids = $.grep(parent_tr.attr("class").split(" "), 
				function(c) { return c.match(/^f\d+$/)});
  rows.each(function () {
    var folderid = "f" + counter++;
    this.id = folderid;
    if (parent_tr) {
      entries.push("#"+folderid);
      $(this).addClass(ancestor_folderids.join(" "));
    }
    $(this).addClass(folderid);
  }).find("span.direxpand").css("cursor", "pointer").click(toggleDir);
  
  if (parent_tr)
    parent_tr.get(0)._entries = entries;
}

// handler for click event on the expander icons
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

// expand action, which either queries the entries or show again the already
// available but hidden entries
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

  $.get(href, {action: "inplace"}, function(data) {
    var rows = $(data.replace(/^<!DOCTYPE[^>]+>/, "")).filter("tr");
    if (rows.length) {
      // remove "Loading ..." row
      tr.next().remove();
      // insert rows corresponding to the folder entries
      rows.children("td.name").css("padding-left", depth);
      enableExpandDir(tr, rows);
      tr.after(rows);
    } else {
      tr.next().find("span.loading").text("").append("<i>(empty)</i>")
        .removeClass("loading");
      enableExpandDir(tr, tr.next());
    }
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
