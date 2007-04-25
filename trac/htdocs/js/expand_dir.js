// Enable expanding/folding folders in TracBrowser

var counter = 0;

function enableExpandDir(elem) {
  elem.find("span.direxpand").click(toggleDir);

  // alert( "queryDir added to " + elem.find("span.direxpand").length + " elements");
}

function toggleDir() {
  var td = $(this).parent();
  if ( $(this).attr("class") == "direxpand" ) {
    $(this).attr("class", "dirfold").attr("title", "Fold directory");
    expandDir(td);
  } else {
    $(this).attr("class", "direxpand").attr("title", "Expand directory");
    foldDir(td);
  }
}

function expandDir(td) {
  var tr = td.parent();
  var a = td.children("a");
  var href = a.attr("href");
  var depth = parseFloat(td.css("padding-left").replace(/^(\d*\.\d*).*$/, "$1")) + 20;
  // insert "Loading ..." row
  tr.after('<tr><td class="name" colspan="5"><span class="loading">Loading ' +
	   a.text() + "...</span></td></tr>");
  tr.next().children("td.name").css("padding-left", depth);

  // prepare the class that will be used by foldDir to remove the folder's entries
  var folderid = "f" + counter++;
  td.addClass(folderid);

  $.get(href, {action: "inplace"}, function(data) {
    // remove "Loading ..." row
    tr.next().remove();
    // insert folder content rows
    var rows = $(data.replace(/^<!DOCTYPE[^>]+>/, "")).filter("tr");
    rows.addClass(folderid);
    rows.children("td.name").css("padding-left", depth);
    enableExpandDir(rows);
    tr.after(rows);
  });
}

function foldDir(td) {
  var folderid = /f\d+/.exec(td.attr("class"))[0];
  td.removeClass(folderid);
  td.parent().parent().children("tr."+folderid).remove();
}
