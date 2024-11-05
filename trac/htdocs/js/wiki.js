(function($){

  // Provides expand/collapse button for central wiki column ($wikipage)
  // within its container ($content).

  window.wikiColumn = function($wikipage) {
    if ($wikipage.length === 0)
      return;
    var $content = $("#content");
    $("<span id='trac-wiki-expander'></span>").on("click", function () {
      $content.toggleClass('narrow');
      if ($content.hasClass('narrow'))
        centerLargeElements();
      else
        resetLargeElements();
    }).prependTo($wikipage);

    // Auto-centering of top-level elements larger than #wikipage's max-width
    var wpow;
    var large_elements;
    var detectLargeElement = function() {
      var $e = $(this);
      if ($e.css('float') !== 'none')
        return 0;
      switch ($e.css('position')) {
        case 'absolute':
        case 'fixed':
          return 0;
      }
      var rol = $e.offset().left - $wikipage.offset().left;
      var excess = $e.outerWidth() + rol - wpow;
      if (excess > 0) {
        $e.data('excess', excess);
        $e.data('rol', rol);
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

      $e.css('margin-left', -shift_left).addClass('trac-wiki-center');
    };
    var resetLargeElements = function() {
      if (large_elements === undefined)
        return;
      $(large_elements)
        .css('margin-left', '')
        .removeClass('trac-wiki-center');
    };
    var detectLargeImage = function() {
      var excess = detectLargeElement.apply(this);
      if (excess > 0)
        centerLargeElement($(this), $wikipage.offset().left);
    };
    var detectLargeElements = function() {
      $wikipage.find("> table, > div").each(detectLargeElement);
      $wikipage.find("> p > a > img").one("load", detectLargeImage).each(
        function() {
          if (this.complete)
            detectLargeImage.apply(this);
        }
      );
    };
    var centerLargeElements = function() {
      if (large_elements === undefined) {
        wpow = $wikipage.outerWidth();
        large_elements = [];
        detectLargeElements();
      }
      var wikipage_left = $wikipage.offset().left;
      $.each(large_elements, function() {
        centerLargeElement($(this), wikipage_left);
      });
    };
    var centerLargeElementsIfNarrow = function() {
      if ($content.hasClass('narrow'))
        centerLargeElements();
    };
    $(window).resize(centerLargeElementsIfNarrow);
    centerLargeElementsIfNarrow();
  };


  jQuery(function($) {
    $("#content").find("h1,h2,h3,h4,h5,h6").addAnchor(_("Link to this section"));
    $("#content").find(".wikianchor").each(function() {
      $(this).addAnchor(babel.format(_("Link to #%(id)s"), {id: $(this).attr('id')}));
    });
    $(".foldable").enableFolding(true, true);
  });

})(jQuery);
