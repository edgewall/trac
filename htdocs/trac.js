function view_history() {
  var history = document.getElementById("wiki-history");
  if (history) {
    if (history.style.visibility != "visible") {
      history.style.visibility = "visible";
    } else {
      history.style.visibility = "hidden";
    }
  }
}

// A better way than for example hardcoding foo.onload
function addEvent(element, type, func){
  if (element.addEventListener) {
    element.addEventListener(type, func, true);
    return true;
  } else if (element.attachEvent) {
    return element.attachEvent("on" + type, func);
  }
  return false;
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
        return unescape(param[1].replace(/\+/g, ' ')).split(/\s+/);
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
        var newNode = node.splitText(pos);
        newNode.nodeValue = newNode.nodeValue.substr(word.length);
        node.parentNode.insertBefore(span, newNode);
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
