function convertDiff(name, table) {
  var ths = table.tHead.rows[0].cells;
  var lines = [
    "Index: " + name,
    "===================================================================",
    "--- " + ths[0].title.substr(5),
    "+++ " + ths[1].title.substr(5),
  ];
  var sepIndex = 0;
  var oldOffset = 0, oldLength = 0, newOffset = 0, newLength = 0;

  for (var i = 0; i < table.tBodies.length; i++) {
    var tBody = table.tBodies[i];
    if (i == 0 || tBody.className == "skipped") {
      if (i > 0) {
        if (!oldOffset && oldLength) oldOffset = 1
        if (!newOffset && newLength) newOffset = 1
        lines[sepIndex] = lines[sepIndex]
          .replace("{1}", oldOffset).replace("{2}", oldLength)
          .replace("{3}", newOffset).replace("{4}", newLength);
      }
      sepIndex = lines.length;
      lines.push("@@ -{1},{2}, +{3},{4} @@");
      oldOffset = 0, oldLength = 0, newOffset = 0, newLength = 0;
      if (tBody.className == "skipped") continue;
    }
    for (var j = 0; j < tBody.rows.length; j++) {
      var cells = tBody.rows[j].cells;
      var oldLineNo = parseInt($(cells[0]).text());
      var newLineNo = parseInt($(cells[1]).text());
      var line = $(cells[2]).text();
      if (isNaN(oldLineNo)) {
        lines.push("+ " + line);
        newLength += 1;
      } else if (isNaN(newLineNo)) {
        lines.push("- " + line);
        oldLength += 1;
      } else {
        lines.push("  " + line);
        oldLength += 1;
        newLength += 1;
        if (!oldOffset) oldOffset = oldLineNo;
        if (!newOffset) newOffset = newLineNo;
      }
    }
  }

  if (!oldOffset && oldLength) oldOffset = 1
  if (!newOffset && newLength) newOffset = 1
  lines[sepIndex] = lines[sepIndex]
    .replace("{1}", oldOffset).replace("{2}", oldLength)
    .replace("{3}", newOffset).replace("{4}", newLength);

  return lines.join("\n");
}

$(document).ready(function() {
  $("div.diff h2").each(function() {
    var switcher = $("<span class='switch'></span>").prependTo(this);
    var name = $.trim($(this).text());
    var table = $(this).next().get(0);
    var pre = $("<pre></pre>").hide().insertAfter(table);
    $("<span>Tabular</span>").click(function() {
      $(pre).hide();
      $(table).show();
      $(this).addClass("active").siblings("span").removeClass("active");
      return false;
    }).addClass("active").appendTo(switcher);
    $("<span>Unified</span>").click(function() {
      $(table).hide();
      if (!pre.get(0).firstChild) pre.text(convertDiff(name, table));
      $(pre).fadeIn("fast")
      $(this).addClass("active").siblings("span").removeClass("active");
      return false;
    }).appendTo(switcher);
  });
});
