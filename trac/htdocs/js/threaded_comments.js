jQuery(document).ready(function($){
  var comments = null;
  var toggle = $('#trac-threaded-toggle');
  toggle.click(function() {
    $(this).toggleClass('checked');
    if ($(this).hasClass('checked')) {
      comments = $("div.change");
      comments.each(function() {
        var children = $("a.follow-up", this).map(function() {
          var cnum = $(this).attr("href").replace('#comment:', '');
          return $('[id^="trac-change-' + cnum + '-"]').get(0);
        });
        if (children.length) {
          var ul = $('<ul class="children"></ul>').appendTo(this);
          children.appendTo(ul).wrap('<li class="child">');
        }
      });
    } else {
      if (comments) {
        $("#changelog").append(comments);
        $("#changelog ul.children").remove();
      }
    }
  });
  if ($("a.follow-up").length)
    toggle.closest("form").show();
});
