(function($){
  var SELECTED_FILE_ELEM = null;
  var ENABLE_KEY_NAV = true;

  $(document).keydown(function(event) {
    if (!ENABLE_KEY_NAV)
      return true;
    var selection = SELECTED_FILE_ELEM;
    switch (event.keyCode) {
      case 74: // j - next line
        if (selection == null) {
          selection = $('#f0');
          if ( !selection.length ) 
            selection = $($("#dirlist tr").get(1))
        } else {
          do {
            selection = selection.next();
          } while (selection.length > 0 && selection.css('display') == 'none');
        }
        break;
      case 75: // k - previous line
        if (selection == null) {
          selection = $('#f0');
        } else {
          do {
            selection = selection.prev();
          } while (selection.length > 0 && selection.css('display') == 'none');
        }
        break;
      case 13: // Enter
      case 65: // 'a'nnotate
      case 79: // 'o'pen
        if (selection != null) {
          var expander = selection.find('.expander');
          if (expander.length > 0) {
            expander.click();
          } else {
            var href = selection.find('a.file').attr('href');
            if (!href)
              href = selection.find('a.parent').attr('href');
            if (href) {
              if (event.keyCode == 65)
                href += '?annotate=blame';
              window.location = href;
            }
          }
        }
        return false;
        break;
      case 76: // 'l'og
        if (selection != null) {
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
    $('a,input,select,textarea,button')
      .focus(function(event) {
        ENABLE_KEY_NAV = false;
      })
      .blur(function(event) {
        ENABLE_KEY_NAV = true;
      });
  });
})(jQuery);
