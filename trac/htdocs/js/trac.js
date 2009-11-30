(function($){
  
  $.fn.addAnchor = function(title) {
    title = title || "Link here";
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
  
  $.loadStyleSheet = function(href, type) {
    type = type || "text/css";
    $(document).ready(function() {
      if (document.createStyleSheet) { // MSIE
        document.createStyleSheet(href);
      } else {
        $("<link rel='stylesheet' type='" + type + "' href='" + href + "' />")
          .appendTo("head");
      }
    });
  }
  
  $.template = function(str) { 
    var args = arguments, kwargs = arguments[arguments.length-1];
    return str.replace(/\${?(\w+)}?/g, function(_, k) {
      if (k.length == 1 && k >= '0' && k <= '9')
        return args[k-'0'];
      else
        return kwargs[k];
    }); 
  }
  
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
