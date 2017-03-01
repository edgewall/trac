(function($){

  if (typeof _ == 'undefined')
    babel.Translations.load({}).install();

  $.fn.addAnchor = function(title) {
    title = title || _("Link here");
    return this.filter("*[id]").each(function() {
      $("<a class='anchor'> \u00B6</a>").attr("href", "#" + this.id)
        .attr("title", title).appendTo(this);
    });
  };

  $.fn.checked = function(checked) {
    if (checked == undefined) { // getter
      if (!this.length) return false;
      return this.get(0).checked;
    } else { // setter
      return this.each(function() {
        this.checked = checked;
      });
    }
  };

  // Add a Select All checkbox to each thead in the table.
  $.fn.addSelectAllCheckboxes = function() {
    var $table = this;
    if ($("tr td.sel", $table).length > 0) {
      $("tr th.sel", $table).append(
        $('<input type="checkbox" name="toggle_group" />').attr({
          title: _("Toggle group")
        }).click(function() {
          $("tr td.sel input",
            $(this).closest("thead, tbody").next())
              .prop("checked", this.checked).change();
        })
      );
      $("tr td.sel", $table).click(function() {
        var $tbody = $(this).closest("tbody");
        var $checkboxes = $("tr td.sel input", $tbody);
        var num_selected = $checkboxes.filter(":checked").length;
        var none_selected = num_selected === 0;
        var all_selected = num_selected === $checkboxes.length;
        $("tr th.sel input", $tbody.prev())
          .prop({"checked": all_selected,
                 "indeterminate": !(none_selected || all_selected)});
      });
    }
  };

  $.fn.exclusiveOnClick = function(selector) {
    var $container = $(this);
    $container.on("click", selector,
      function(event) {
        if (!event.metaKey && !event.altKey)
          return;
        var clicked;
        if (this.tagName === "LABEL") {
          if (this.htmlFor) {
            clicked = document.getElementById(this.htmlFor);
          } else {
            clicked = this.children[0];
          }
        } else {
          clicked = this;
        }
        var $clicked = $(clicked);
        $container.find(":checkbox").not(clicked).prop("checked", false);
        $clicked.prop("checked", true);
      }).mousedown(function(event) {
        if (event.metaKey || event.altKey) {
          event.preventDefault(); // Prevent border on Firefox.
        }
      });
  };

  // Conditionally disable the submit button. Returns a jQuery object.
  $.fn.disableSubmit = function(determinant) {
    determinant = $(determinant);
    var subject = $(this);
    var isDisabled;
    if (determinant.is("input:checkbox")) {
      isDisabled = function () {
          return determinant.filter(":checked").length === 0;
      }
    } else if (determinant.is("input:file")) {
      isDisabled = function () {
          return !determinant.val();
      }
    } else {
      return subject;
    }
    function toggleDisabled() {
      subject.prop("disabled", isDisabled);
      if (subject.prop("disabled")) {
        subject.attr("title", _("At least one item must be selected"))
      } else {
        subject.removeAttr("title");
      }
    }
    determinant.change(toggleDisabled);
    toggleDisabled();
    return subject;
  };

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
  };

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
  };

  $.fn.scrollToTop = function() {
    return this.each(function() {
      scrollTo(0, $(this).getAbsolutePos()[0].top);
      return false;
    });
  };

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
  };

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

  var warn_unsaved_changes;

  // Prompt a warning if leaving the page with unsaved changes
  $.setWarningUnsavedChanges = function(enabled, message) {
    if (enabled) {
      if (!warn_unsaved_changes) {
        $(window).bind("beforeunload", function() {
          return warn_unsaved_changes;
        });
      }
      warn_unsaved_changes = message || _("You have unsaved changes. Your " +
        "changes will be lost if you leave this page before saving your " +
        "changes.");
    } else {
      $(window).unbind("beforeunload");
      warn_unsaved_changes = null;
    }
  };

  // Escape special HTML characters (&<>")
  var quote = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"};

  $.htmlEscape = function(value) {
    if (typeof value != "string")
      return value;
    return value.replace(/[&<>"]/g, function(c) { return quote[c]; });
  };

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
  };

  $.htmlFormat = function(str) {
    return format(str, arguments, $.htmlEscape);
  };

  $.template = $.format;    // For backward compatibility

  // Used for dynamically updating the height of a textarea
  window.resizeTextArea = function (id, rows) {
    var textarea = $("#" + id).get(0);
    if (!textarea || textarea.rows == undefined) return;
    $(textarea).height("");
    textarea.rows = rows;
  }

})(jQuery);
