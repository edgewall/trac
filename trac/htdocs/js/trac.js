(function($){

  if (typeof _ == 'undefined')
    babel.Translations.load({}).install();

  $.fn.addAnchor = function(title) {
    title = title || _("Link here");
    return this.filter("*[id]").each(function() {
      $("<a class='anchor'> \u00B6</a>").attr("href", "#" + this.id)
        .attr("title", title).appendTo(this);
    });
  }

  $.fn.checked = function(checked) {
    if (checked == undefined) { // getter
      if (!this.length) return false;
      return this.get(0).checked;
    } else { // setter
      return this.each(function() {
        this.checked = checked;
      });
    }
  }

  $.fn.enable = function(enabled) {
    if (enabled == undefined) enabled = true;
    return this.each(function() {
      this.disabled = !enabled;
      var label = $(this).parents("label");
      if (!label.length && this.id) {
        label = $("label[for='" + this.id + "']");
      }
      if (!enabled) {
        label.addClass("disabled");
      } else {
        label.removeClass("disabled");
      }
    });
  }

  $.fn.getAbsolutePos = function() {
    return this.map(function() {
      var left = this.offsetLeft;
      var top = this.offsetTop;
      var parent = this.offsetParent;
      while (parent) {
        left += parent.offsetLeft;
        top += parent.offsetTop;
        parent = parent.offsetParent;
      }
      return {left: left, top: top};
    });
  }

  $.fn.scrollToTop = function() {
    return this.each(function() {
      scrollTo(0, $(this).getAbsolutePos()[0].top);
      return false;
    });
  }

  // Disable the form's submit action after the submit button is pressed by
  // replacing it with a handler that cancels the action. The handler is
  // removed when navigating away from the page so that the action will
  // be enabled when using the back button to return to the page.
  $.fn.disableOnSubmit = function() {
    this.click(function() {
      var form = $(this).closest("form");
      if (form.hasClass("trac-submit-is-disabled")) {
        form.bind("submit.prevent-submit", function() {
          return false;
        });
        $(window).on("unload", function() {
          form.unbind("submit.prevent-submit");
        });
      } else {
        form.addClass("trac-submit-is-disabled");
        $(window).on("unload", function() {
          form.removeClass("trac-submit-is-disabled");
        })
      }
    });
  }

  $.loadStyleSheet = function(href, type) {
    type = type || "text/css";
    $(document).ready(function() {
      var link;
      $("link[rel=stylesheet]").each(function() {
        if (this.getAttribute("href") === href) {
          if (this.disabled)
            this.disabled = false;
          link = this;
          return false;
        }
      });
      if (link !== undefined)
        return;
      if (document.createStyleSheet) { // MSIE
        document.createStyleSheet(href);
      } else {
        $("<link rel='stylesheet' type='" + type + "' href='" + href + "' />")
          .appendTo("head");
      }
    });
  };

  // {script.src: [listener1, listener2, ...]}
  var readyListeners = {};

  $.documentReady = function(listener) {
    var script = document.currentScript;
    if (script === undefined) {
      script = $("head script");
      script = script[script.length - 1];
    }
    if (script) {
      var href = script.getAttribute("src");
      if (!(href in readyListeners))
        readyListeners[href] = [];
      var listeners = readyListeners[href];
      listeners.push(listener);
    }
    $(document).ready(listener);
  };

  $.loadScript = function(href, type, charset) {
    var script;
    $("head script").each(function() {
      if (this.getAttribute("src") === href) {
        script = this;
        return false;
      }
    });
    if (script !== undefined) {
      // Call registered ready listeners
      $.each(readyListeners[href] || [], function(idx, listener) {
        listener.call(document, $);
      });
    } else {
      // Don't use $("<script>").appendTo("head") to avoid adding
      // "_=<timestamp>" parameter to url.
      script = document.createElement("script");
      script.src = href;
      script.async = false;
      script.type = type || "text/javascript";
      script.charset = charset || "utf-8";
      $("head")[0].appendChild(script);
    }
  };

  // Escape special HTML characters (&<>")
  var quote = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"};

  $.htmlEscape = function(value) {
    if (typeof value != "string")
      return value;
    return value.replace(/[&<>"]/g, function(c) { return quote[c]; });
  }

  function format(str, args, escape) {
    var kwargs = args[args.length - 1];
    return str.replace(/\${?(\w+)}?/g, function(_, k) {
      var result;
      if (k.length == 1 && k >= '0' && k <= '9')
        result = args[k - '0'];
      else
        result = kwargs[k];
      return escape ? escape(result) : result;
    });
  }

  // Expand positional ($1 .. $9) and keyword ($name) arguments in a string.
  // The htmlFormat() version HTML-escapes arguments prior to substitution.
  $.format = function(str) {
    return format(str, arguments);
  }

  $.htmlFormat = function(str) {
    return format(str, arguments, $.htmlEscape);
  }

  $.template = $.format;    // For backward compatibility

  // Used for dynamically updating the height of a textarea
  window.resizeTextArea = function (id, rows) {
    var textarea = $("#" + id).get(0);
    if (!textarea || textarea.rows == undefined) return;
    $(textarea).height("");
    textarea.rows = rows;
  }

  // The following are defined for backwards compatibility with releases prior
  // to Trac 0.11

  window.addEvent = function(elem, type, func) {
    $(elem).bind(type, func);
  }
  window.addHeadingLinks = function(container, title) {
    $.each(["h1", "h2", "h3", "h4", "h5", "h6"], function() {
      $(this, container).addAnchor(title);
    });
  }
  window.enableControl = function(id, enabled) {
    $("#" + id).enable(enabled);
  }
  window.getAncestorByTagName = function(elem, tagName) {
    return $(elem).parents(tagName).get(0);
  }

})(jQuery);
