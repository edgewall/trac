(function($){

  // Provides expand/collapse button for central wiki column ($wikipage)
  // within its container ($content).

  window.wikiColumn = function($wikipage) {
    var $content = $("#content");
    $("<span id='trac-wiki-expander'></span>").on("click", function () {
      $content.toggleClass('narrow');
      if ($content.hasClass('narrow'))
        centerLargeElements();
      else
        resetLargeElements();
    }).prependTo($wikipage);

    // Auto-centering of top-level elements larger than #wikipage's max-width
    var wpow = $wikipage.outerWidth();
    var large_elements = [];
    var detectLargeElement = function() {
      var rol = $(this).offset().left - $wikipage.offset().left;
      var excess = $(this).outerWidth() + rol - wpow;
      if (excess > 0) {
        $(this).data('excess', excess);
        $(this).data('rol', rol);
        large_elements.push(this);
      }
      return excess;
    };
    var centerLargeElement = function($e, wpleft) {
        var shift_left;
        var excess = $e.data('excess');
        var rol = $e.data('rol');
        if (excess > rol)
            shift_left = rol + (excess - rol) / 2;
        else
            shift_left = excess;
        if (shift_left > wpleft)
          shift_left = wpleft;

        $e.css({'margin-left': -shift_left,
                'background': 'rgba(255, 255, 255, .8)'});
    };
    var resetLargeElements = function() {
      for (var i = 0; i < large_elements.length; i++) {
        $(large_elements[i]).css({'margin-left': 0, 'background': 'none'});
      }
    };
    var detectLargeImage = function() {
      var excess = detectLargeElement.apply(this);
      if (excess > 0)
        centerLargeElement($(this), $wikipage.offset().left);
    };
    $("#wikipage > table").each(detectLargeElement);
    $("#wikipage > div").each(detectLargeElement);
    $("#wikipage > p > a > img").one("load", detectLargeImage).each(
      function() {
        if (this.complete)
          detectLargeImage.apply(this);
      }
    );

    var centerLargeElements = function() {
      var wikipage_left = $wikipage.offset().left;
      for (var i = 0; i < large_elements.length; i++)
        centerLargeElement($(large_elements[i]), wikipage_left);
    };
    $(window).resize(centerLargeElements);
    centerLargeElements();
  };


  jQuery(function($) {
    $("#content").find("h1,h2,h3,h4,h5,h6").addAnchor(_("Link to this section"));
    $("#content").find(".wikianchor").each(function() {
      $(this).addAnchor(babel.format(_("Link to #%(id)s"), {id: $(this).attr('id')}));
    });
    $(".foldable").enableFolding(true, true);
  });

})(jQuery);
