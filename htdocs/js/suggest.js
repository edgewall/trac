/*
 Text field auto-completion plugin for jQuery.
 Based on http://www.dyve.net/jquery/?autocomplete by Dylan Verheul.
*/
$.suggest = function(input, url, paramName, minChars, delay) {
  var input = $(input).addClass("suggest").attr("autocomplete", "off");
  var offset = getOffset(input);
  var results = $("<div>").addClass("suggestions").css({
    position: "absolute",
    top:  (offset.y + input.get(0).offsetHeight) + "px",
    left: offset.x + "px"
  }).hide().appendTo("body");
  var timeout = null;
  var prev = "";
  var selectedIndex = -1;

  input
    .blur(function() {
      if (timeout) clearTimeout(timeout);
      timeout = setTimeout(hide, 200);
    })
    .keydown(function(e) {
      switch(e.keyCode) {

        case 27: // escape
          hide();
          break;

        case 38: // up
        case 40: // down
          e.preventDefault();
          if (results.is(":visible")) {
            var items = $("li", results);
            if (!items) return;
            var index = selectedIndex + (e.keyCode == 38 ? -1 : 1);
            if (index >= 0 && index < items.length) {
              move(index);
            }
          } else {
            show();
          }
          break;

        case 9:  // tab
        case 13: // return
          var li = $("li.selected", results);
          if (li.length) {
            select(li);
            e.preventDefault();
          }
          break;

        default:
          selectedIndex = -1;
          if (timeout) clearTimeout(timeout);
          timeout = setTimeout(show, delay);
          break;
      }
    });

  function hide() {
    if (timeout) clearTimeout(timeout);
    input.removeClass("loading");
    if (results.is(":visible")) {
      results.hide();
    }
  }

  function move(index) {
    items = $("li", results);
    items.removeClass("selected");
    $(items[index]).addClass("selected");
    selectedIndex = index;
  }

  function select(li) {
    if (!li) li = $("<li>");
    else li = $(li);
    var val = $.trim(li.html());
    prev = val;
    results.html("");
    input.val(val);
    hide();
    selectedIndex = -1;
  }

  function show() {
    var val = input.val();
    if (val == prev) return;
    prev = val;
    if (val.length >= minChars) {
      input.addClass("loading");
      var params = {};
      params[paramName] = val;
      $.get(url, params, function(data) {
        if (data) {
          if ($.browser.msie) {
            results.html("");
            results
              .append(document.createElement("iframe"))
              .append($("<div>").html(data).css("z-index", "101"));
          } else {
            results.html(data);
          }
          results.fadeTo("fast", 0.95);
          items = $("li", results);
          items
            .hover(function() { move(items.index(this)) },
                   function() { $(this).removeClass("selected") })
            .click(function() { select(this) });
          move(0);
        } else {
          hide();
        }
      });
    } else {
      results.hide();
    }
  }
}

$.fn.suggest = function(url, paramName, minChars, delay) {
  url = url || window.location.pathname;
  paramName = paramName || 'q';
  minChars = minChars || 1;
  delay = delay || 400;
  return this.each(function() {
    new $.suggest(this, url, paramName, minChars, delay);
  });
}
