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

function enableControl(id, enabled) {
  if (typeof(enabled) == "undefined") enabled = true;
  var control = document.getElementById(id);
  if (!control) return;
  control.disabled = !enabled;
  var labels = document.getElementsByTagName("label");
  for (var i = 0; i < labels.length; i++) {
    if (labels[i].htmlFor == id) {
      labels[i].className = enabled ? "enabled" : "disabled";
    }
  }
}

function addWikiFormattingToolbar(textarea) {
  if ((typeof(document["selection"]) == "undefined")
   && (typeof(textarea["setSelectionRange"]) == "undefined")) {
    return;
  }
  
  var toolbar = document.createElement("div");
  toolbar.className = "wikitoolbar";

  function addButton(id, title, fn) {
    var a = document.createElement("a");
    a.href = "#";
    a.id = id;
    a.title = title;
    a.onclick = function() { try { fn() } catch (e) { } return false };
    a.tabIndex = 400;
    toolbar.appendChild(a);
  }

  function encloseSelection(prefix, suffix) {
    textarea.focus();
    var start, end, sel, scrollPos, subst;
    if (typeof(document["selection"]) != "undefined") {
      sel = document.selection.createRange().text;
    } else if (typeof(textarea["setSelectionRange"]) != "undefined") {
      start = textarea.selectionStart;
      end = textarea.selectionEnd;
      scrollPos = textarea.scrollTop;
      sel = textarea.value.substring(start, end);
    }
    if (sel.match(/ $/)) { // exclude ending space char, if any
      sel = sel.substring(0, sel.length - 1);
      suffix = suffix + " ";
    }
    subst = prefix + sel + suffix;
    if (typeof(document["selection"]) != "undefined") {
      var range = document.selection.createRange().text = subst;
      textarea.caretPos -= suffix.length;
    } else if (typeof(textarea["setSelectionRange"]) != "undefined") {
      textarea.value = textarea.value.substring(0, start) + subst +
                       textarea.value.substring(end);
      if (sel) {
        textarea.setSelectionRange(start + subst.length, start + subst.length);
      } else {
        textarea.setSelectionRange(start + prefix.length, start + prefix.length);
      }
      textarea.scrollTop = scrollPos;
    }
  }

  addButton("strong", "Bold text: '''Example'''", function() {
    encloseSelection("'''", "'''");
  });
  addButton("em", "Italic text: ''Example''", function() {
    encloseSelection("''", "''");
  });
  addButton("heading", "Heading: == Example ==", function() {
    encloseSelection("\n== ", " ==\n", "Heading");
  });
  addButton("link", "Link: [http://www.example.com/ Example]", function() {
    encloseSelection("[", "]");
  });
  addButton("code", "Code block: {{{ example }}}", function() {
    encloseSelection("\n{{{\n", "\n}}}\n");
  });
  addButton("hr", "Horizontal rule: ----", function() {
    encloseSelection("\n----\n", "");
  });

  textarea.parentNode.insertBefore(toolbar, textarea);
  var br = document.createElement("br");
  br.style.clear = "left";
  textarea.parentNode.insertBefore(br, textarea);
}
