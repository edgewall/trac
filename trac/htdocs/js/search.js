(function($){

  /* Adapted from http://www.kryogenix.org/code/browser/searchhi/ */
  $.fn.highlightText = function(text, className, caseSensitive) {
    function highlight(node) {
      if (node.nodeType == 3) { // Node.TEXT_NODE
        var val = node.nodeValue;
        var pos = (caseSensitive ? val : val.toLowerCase()).indexOf(text);
        if (pos >= 0 && !$(node.parentNode).hasClass(className)) {
          var span = document.createElement("span");
          span.className = className;
          var txt = document.createTextNode(val.substr(pos, text.length));
          span.appendChild(txt);
          node.parentNode.insertBefore(span, node.parentNode.insertBefore(
            document.createTextNode(val.substr(pos + text.length)),
              node.nextSibling));
          node.nodeValue = val.substr(0, pos);
        }
      } else if (!$(node).is("button, select, textarea")) {
        $.each(node.childNodes, function() { highlight(this) });
      }
    }
    return this.each(function() { highlight(this) });
  };

  $(document).ready(function() {
    $("p.filters").exclusiveOnClick(":checkbox, :checkbox + label");

    var elems = $(".searchable");
    if (!elems.length) return;

    function getSearchTerms(url) {
      if (url.indexOf("?") == -1) return [];
      var params = url.substr(url.indexOf("?") + 1).split("&");
      for (var p in params) {
        var param = params[p].split("=");
        if (param.length < 2) continue;
        if (param[0] == "q" || param[0] == "p") {// q= for Google, p= for Yahoo
          var query = decodeURIComponent(param[1].replace(/\+/g, " "));
          if (query[0] == "!") query = query.slice(1);
          var terms = [];
          $.each(query.split(/(".*?"|'.*?'|\s+)/), function() {
            if (terms.length < 10) {
              var term = this.replace(/^\s+$/, "")
                         .replace(/^['"]/, "")
                         .replace(/['"]$/, "");
              if (term.length >= 3)
                terms.push(term);
            }
          });
          return terms;
        }
      }
      return [];
    }

    var terms = getSearchTerms(document.URL);
    if (!terms.length) terms = getSearchTerms(document.referrer);
    if (terms.length) {
      $.each(terms, function(idx) {
        elems.highlightText(this.toLowerCase(), "searchword" + (idx % 5));
      });
    } else {
      function scrollToHashSearchMatch() {
        var h = window.location.hash;
        var direction = h[1];
        var case_insensitive = h.match(/\/i$/);
        if (direction == '/' || direction == '?') {
          var hterm = h.substr(2);
          if (case_insensitive)
            hterm = hterm.substr(0, hterm.length - 2).toLowerCase();
          $('.searchword0').each(function() {
            $(this).after($(this).html()).remove();
          });
          elems.highlightText(hterm, "searchword0", !case_insensitive);
          var hmatches = $('.searchword0');
          if (direction == '?')
            hmatches = hmatches.last();
          hmatches.first().each(function() {
            var offset = $(this).offset().top;
            window.scrollTo(0, offset);
          });
        }
      }
      window.onhashchange = scrollToHashSearchMatch;
      scrollToHashSearchMatch();
    }
  });

})(jQuery);
