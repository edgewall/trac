// Used for dynamically updating the height of a textarea
function resizeTextArea(id, rows) {
  var textarea = document.getElementById(id);
  if (!textarea || (typeof(textarea.rows) == "undefined")) return;
  textarea.rows = rows;
}

// A better way than for example hardcoding foo.onload
function addEvent(element, type, func){
  if (element.addEventListener) {
    element.addEventListener(type, func, false);
    return true;
  } else if (element.attachEvent) {
    return element.attachEvent("on" + type, func);
  }
  return false;
}

// Convenience function for the nearest ancestor element with a specific tag
// name
function getAncestorByTagName(e, tagName) {
  tagName = tagName.toLowerCase();
  do {
    e = e.parentNode;
  } while ((e.nodeType == 1) && (e.tagName.toLowerCase() != tagName));
  return (e.nodeType == 1) ? e : null;
}

// Adapted from http://www.kryogenix.org/code/browser/searchhi/
function searchHighlight() {
  if (!document.createElement) return;

  var div = document.getElementById("searchable");
  if (!div) return;

  function getSearchWords(url) {
    if (url.indexOf('?') == -1) return [];
    var queryString = url.substr(url.indexOf('?') + 1);
    var params = queryString.split('&');
    for (var p in params) {
      var param = params[p].split('=');
      if (param.length < 2) continue;
      if (param[0] == 'q' || param[0] == 'p') { // q= for Google, p= for Yahoo
        var query = decodeURIComponent(param[1].replace(/\+/g, ' '));
        if (query[0] == '!') query = query.slice(1);
        words = query.split(/(".*?")|('.*?')|(\s+)/);
        var words2 = new Array();
        for (var w in words) {
          words[w] = words[w].replace(/^\s+$/, '');
          if (words[w] != '') {
            words2.push(words[w].replace(/^['"]/, '').replace(/['"]$/, ''));
          }
        }
        return words2;
      }
    }
    return [];
  }

  function highlightWord(node, word, searchwordindex) {
    // If this node is a text node and contains the search word, highlight it by
    // surrounding it with a span element
    if (node.nodeType == 3) { // Node.TEXT_NODE
      var pos = node.nodeValue.toLowerCase().indexOf(word.toLowerCase());
      if (pos >= 0 && !/^searchword\d$/.test(node.parentNode.className)) {
        var span = document.createElement("span");
        span.className = "searchword" + (searchwordindex % 5);
        span.appendChild(document.createTextNode(
          node.nodeValue.substr(pos, word.length)));
        node.parentNode.insertBefore(span, node.parentNode.insertBefore(
          document.createTextNode(node.nodeValue.substr(pos + word.length)),
            node.nextSibling));
        node.nodeValue = node.nodeValue.substr(0, pos);
        return true;
      }
    } else if (!node.nodeName.match(/button|select|textarea/i)) {
      // Recurse into child nodes
      for (var i = 0; i < node.childNodes.length; i++) {
        if (highlightWord(node.childNodes[i], word, searchwordindex)) i++;
      }
    }
    return false;
  }

  var words = getSearchWords(document.URL);
  if (!words.length) words = getSearchWords(document.referrer);
  if (words.length) {
    for (var w in words) {
      if (words[w].length) highlightWord(div, words[w], w);
    }
  }
}

function enableControl(id, enabled) {
  if (typeof(enabled) == "undefined") enabled = true;
  var control = document.getElementById(id);
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
  var base = document.location.pathname;
  function addLinks(elems) {
    for (var i = 0; i < elems.length; i++) {
      var hn = elems[i];
      if (hn.id) {
        var link = document.createElement('a');
        link.href = base + '#' + hn.id;
        link.className = 'anchor';
        link.title = title.replace(/\$id/, hn.id);
        link.appendChild(document.createTextNode(" \u00B6"));
        hn.appendChild(link);
      }
    }
  }
  for (var lvl = 0; lvl <= 6; lvl++) {
    addLinks(container.getElementsByTagName('h' + lvl));
  }
}
