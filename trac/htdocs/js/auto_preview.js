// Automatic form submission and preview through XHR

(function($) {
  // Enable automatic submission of forms.
  //
  // This method can be applied to a single form, where it enables
  // auto-submission on all the editable elements that it contains.
  // It can also be applied on a list of elements, in which case it
  // enables auto-submission only for these elements.
  //
  // Arguments:
  //  - `args`: additional form data to be passed with the XHR.
  //  - `update`: the function that is called with the submission reply. It
  //              is called with the request data and the reply.
  //  - `busy`: an object or jQuery selector to be shown while requesting an
  //            update.
  $.fn.autoSubmit = function(args, update, busy) {
    if (this.length == 0 || auto_preview_timeout <= 0)
      return this;
    if (this[0].nodeName == 'FORM') {
      var form = this;
      var inputs = this.find("textarea, select, :text, :checkbox, :radio");
    } else {
      var form = this.closest('form');
      var inputs = this;
    }
    var timeout = auto_preview_timeout * 1000;
    var timer = null;
    var updating = false;
    var queued = false;
    
    // Return true iff the values have changed
    function values_changed(new_values) {
      if (values.length != new_values.length)
        return true;
      for (var i in values) {
        var value = values[i], new_value = new_values[i];
        if ((value.name != new_value.name) || (value.value != new_value.value))
          return true;
      }
      return false;
    }
    
    // Request a preview through XHR
    function request() {
      if (!updating) {
        var new_values = form.serializeArray();
        if (values_changed(new_values)) {
          values = new_values;
          updating = true;
          if (busy != undefined)
            $(busy).show();
          
          // Construct request data
          var data = values.slice(0);
          for (var key in args)
            data.push({name: key, value: args[key]});
          
          $.ajax({
            type: form.attr('method'), url: form.attr('action'),
            data: data, traditional: true, dataType: "html",
            success: function(reply) {
              if (queued)
                timer = setTimeout(request, timeout);
              updating = false;
              queued = false;
              if (busy != undefined)
                $(busy).hide();
              update(data, reply);
            },
            error: function(req, err, exc) {
              updating = false;
              queued = false;
              if (busy != undefined)
                $(busy).hide();
            }
          });
        }
      }
    }
    
    // Trigger a request after the given timeout
    function trigger() {
      if (!updating) {
        if (timer)
          clearTimeout(timer);
        timer = setTimeout(request, timeout);
      } else {
        queued = true;
      }
      return true;
    }

    var values = form.serializeArray();
    return inputs.each(function() {
      $(this).keydown(trigger).keypress(trigger).change(trigger).blur(trigger);
    });
  };

  // Enable automatic previewing to <textarea> elements.
  //
  // Arguments:
  //  - `href`: URL to be called for fetching the preview data.
  //  - `args`: arguments to be passed with the XHR.
  //  - `update`: the function that is called with the preview results. It
  //              is called with the textarea, the text that was rendered and
  //              the rendered text.
  $.fn.autoPreview = function(href, args, update) {
    if (auto_preview_timeout <= 0)
      return this;
    var timeout = auto_preview_timeout * 1000;
    return this.each(function() {
      var timer = null;
      var updating = false;
      var textarea = this;
      var data = {};
      for (var key in args)
        data[key] = args[key];
      data["__FORM_TOKEN"] = form_token;
      data["text"] = textarea.value;
      
      // Request a preview through XHR
      function request() {
        var text = textarea.value;
        if (!updating && (text != data["text"])) {
          updating = true;
          data["text"] = text;
          $.ajax({
            type: "POST", url: href, data: data, dataType: "html",
            success: function(data) {
              updating = false;
              update(textarea, text, data);
              if (textarea.value != text)
                timer = setTimeout(request, timeout);
            },
            error: function(req, err, exc) {
              updating = false;
            }
          });
        }
      }
      
      // Trigger a request after the given timeout
      function trigger() {
        if (!updating) {
          if (timer)
            clearTimeout(timer);
          timer = setTimeout(request, timeout);
        }
        return true;
      }
      
      $(this).keydown(trigger).keypress(trigger).blur(trigger);
    });
  };
})(jQuery);
