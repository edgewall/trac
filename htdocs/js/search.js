// Adapted from http://www.kryogenix.org/code/browser/searchhi/
function searchHighlight() {
  var elems = $(".searchable");
  if (!elems.length) return;

  function getSearchWords(url) {
    if (url.indexOf("?") == -1) return [];
    var params = url.substr(url.indexOf("?") + 1).split("&");
    for (var p in params) {
      var param = params[p].split("=");
      if (param.length < 2) continue;
      if (param[0] == "q" || param[0] == "p") { // q= for Google, p= for Yahoo
        var query = decodeURIComponent(param[1].replace(/\+/g, " "));
        if (query[0] == "!") query = query.slice(1);
        var words = [];
        $.each(query.split(/(".*?")|('.*?')|(\s+)/), function() {
          word = this.replace(/^\s+$/, "");
          if (word.length) {
            words.push(this.replace(/^['"]/, "").replace(/['"]$/, ""));
          }
        });
        return words;
      }
    }
    return [];
  }

  function highlightWord(node, word, index) {
    // If this node is a text node and contains the search word, highlight it by
    // surrounding it with a span element
    if (node.nodeType == 3) { // Node.TEXT_NODE
      var text = node.nodeValue;
      var pos = text.toLowerCase().indexOf(word);
      if (pos >= 0 && !/^searchword\d$/.test(node.parentNode.className)) {
        var span = document.createElement("span");
        span.className = "searchword" + (index % 5);
        span.appendChild(document.createTextNode(text.substr(pos, word.length)));
        node.parentNode.insertBefore(span, node.parentNode.insertBefore(
          document.createTextNode(text.substr(pos + word.length)),
            node.nextSibling));
        node.nodeValue = text.substr(0, pos);
        return true;
      }
    } else if (!$(node).is("button, select, textarea")) {
      $.each(node.childNodes, function() { highlightWord(this, word, index) });
    }
    return false;
  }

  var words = getSearchWords(document.URL);
  if (!words.length) words = getSearchWords(document.referrer);
  if (words.length) {
    for (var w in words) {
      elems.each(function() { highlightWord(this, words[w].toLowerCase(), w) });
    }
  }
}

$(document).ready(searchHighlight);
