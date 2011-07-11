// Automatic preview through XHR

(function($) {
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
  }
})(jQuery);
