// Used for dynamically updating the height of a textarea
function resizeTextArea(id, rows) {
  var textarea = $(id).get(0);
  if (!textarea || textarea.rows == undefined) return;
  textarea.rows = rows;
}

function addEvent(elem, type, func) {
  $(elem).bind(type, func);
}

// Convenience function for the nearest ancestor element with a specific tag
// name
function getAncestorByTagName(elem, tagName) {
  return $(elem).ancestors(tagName).get(0);
}

function enableControl(id, enabled) {
  if (enabled == undefined) enabled = true;
  var control = $("#" + id).get(0);
  if (!control) return;
  control.disabled = !enabled;
  var label = getAncestorByTagName(control, "label");
  if (label) {
    label.className = enabled ? "enabled" : "disabled";
  } else {
    var labels = document.getElementsByTagName("label");
    for (var i = 0; i < labels.length; i++) {
      if (labels[i].htmlFor == id) {
        labels[i].className = enabled ? "enabled" : "disabled";
        break;
      }
    }
  }
}

function addHeadingLinks(container, title) {
  for (var lvl = 0; lvl <= 6; lvl++) {
    $("h" + lvl + "[@id]", container).each(function() {
      $(this).append("<a class=anchor title='" + title.replace(/\$id/, this.id) +
        "' href='#" + this.id + "'> \u00B6</a>");
    });
  }
}
