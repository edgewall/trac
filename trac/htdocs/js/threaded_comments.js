/* Threaded ticket comments
   ========================

   See the #prefs form in ticket.html.

   We have three mutually exclusive orders, 'newest' first, 'oldest'
   first and 'threaded'.  In addition, changes without comments can be
   filtered out.

   When switching to 'threaded', the changes without comments must be
   shown again as they can also have a follow-up. After appending
   eventual children, they must be hidden again and `:has(.comment)`
   will now take into account the threaded comments in
   children. Likewise, when switching away from 'threaded' to a linear
   order, the changes without comments need to be hidden again.
 */
jQuery(document).ready(function($){
  var comments = null;
  var order = null;
  var form = $("#prefs");
  var $trac_comments_order = form.find("input[name='trac-comments-order']");

  var commentsOnly = $("#trac-comments-only-toggle");
  var applyCommentsOnly = function() {
    if (commentsOnly.attr('checked')) {
      $("div.change:not(.trac-new):not(:has(.trac-field-attachment)) ul.changes").hide();
      $("div.change:not(.trac-new):not(:has(.trac-field-attachment)):not(:has(.comment))").hide();
    } else {
      $("div.change ul.changes").show();
      $("div.change").show();
    }
  };

  window.applyCommentsOrder = function(new_order) {
    $trac_comments_order.val([new_order]);
    applyOrder(new_order);
  };
  var applyOrder = function(new_order) {
    applyCommentsOnly();
    order = new_order;
    if (order == 'newest') {
      $("#changelog").append($("div.change").get().reverse());
    } else if (order == 'threaded') {
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
    }
  };
  var unapplyOrder = function() {
    if (order == 'newest') {
      $("#changelog").append($("div.change").get().reverse());
    } else if (order == 'threaded') {
      if (comments) {
        $("#changelog").append(comments);
        $("#changelog ul.children").remove();
      }
    }
  };

  if ($("a.follow-up").length)
    $('#trac-threaded-toggle').show();
  else if (comments_prefs.comments_order == 'threaded')
    comments_prefs.comments_order = 'oldest'

  var savePrefs = function(key, value) {
    var data = {
      save_prefs: true,
      __FORM_TOKEN: form_token
    };
    data[key] = value;
    $.ajax({ url: form.attr('action'), type: 'POST', data: data, dataType: 'text' });
  };

  commentsOnly.attr('checked', comments_prefs.comments_only != 'false');
  commentsOnly.click(function() {
    applyCommentsOnly();
    savePrefs('ticket_comments_only', !!commentsOnly.attr('checked'));
  });

  applyCommentsOrder(comments_prefs.comments_order);
  $trac_comments_order.change(function() {
    unapplyOrder();
    applyOrder($trac_comments_order.filter(":checked").val());
    savePrefs('ticket_comments_order', order);
  });
});
