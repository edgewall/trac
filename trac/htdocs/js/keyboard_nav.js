(function($){
  var SELECTED_FILE_ELEM = null;
  var LAST_HOVERED_FILE_ELEM = null;
  var ENABLE_KEY_NAV = true;

  $(document).keydown(function(event) {
    if (!ENABLE_KEY_NAV)
      return true;
    if (event.ctrlKey)
      return true; // let CTRL+R do its job

    var selection = SELECTED_FILE_ELEM;
    function pickFirst() {
      selection = $('#f0');
      if ( !selection.length )
        selection = $("#dirlist tr:first");
    }
    function pickCurrent() {
      selection = LAST_HOVERED_FILE_ELEM;
      if ( selection == null )
        pickFirst();
    }

    switch (event.which) {
      case 74: // 'j' - next line
        if ( selection == null )
          pickFirst();
        else
          do {
            selection = selection.next();
          } while (selection.length > 0 && selection.css("display") == 'none');
        break;
      case 75: // 'k' - previous line
        if ( selection == null )
          pickFirst();
        else
          do {
            selection = selection.prev();
          } while (selection.length > 0 && selection.css("display") == 'none');
        break;
      case 13: // <Enter>
      case 65: // 'A'nnotate
      case 79: // 'o'pen
      case 82: // 'r'eload
      case 86: // 'v'iew
        if (selection == null)
          pickCurrent();

        var expander = selection.find('.expander');
        if (expander.length > 0) {
          if (event.keyCode == 82) { // 'r'eload
            selection.removeClass("expanded").removeClass("collapsed")
              .siblings("tr."+selection.get(0).id).not(selection).remove();
          }
          expander.click();
        } else {
          var href = selection.find('a.file').attr('href');
          if (!href)
            href = selection.find('a.parent').attr('href');
          if (href) {
            if (event.keyCode == 65) // 'a'nnotate also ok for now
              href += (href.indexOf("?")>-1?'&':'?') + 'annotate=blame';
            window.location = href;
          }
        }
        return false;
        break;
      case 76: // 'L'og
        if (event.shiftKey && selection != null) {
          var href = selection.find('td.rev a').attr('href');
          if (href)
            window.location = href;
        }
        break;
      default:
        return true;
    }
    if (selection.length > 0) {
      if (SELECTED_FILE_ELEM != null)
        SELECTED_FILE_ELEM.removeClass('focus');
      selection.addClass('focus');
      SELECTED_FILE_ELEM = selection;
    }
    return false;
  });

  $(function() {
    $('a,input,select,textarea,button').bind({
      focus: function() { ENABLE_KEY_NAV = false; },
      blur: function() { ENABLE_KEY_NAV = true; }
    });
    $("#dirlist tr").live('mouseenter', function() {
      LAST_HOVERED_FILE_ELEM = $(this);
    });
  });
})(jQuery);
