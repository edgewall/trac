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
  var comment_controls_always_visible = false;

  // "Show property changes" control
  var $show_prop_changes = $("#trac-show-property-changes-toggle");
  var applyShowPropertyChanges = function() {
    if ($show_prop_changes.prop('checked')) {
      // Simply show all
      $("div.change .changes").show();
      $("div.change").show();
    } else {
      // Hide the property changes, except for new changes, and attachments
      $("div.change:not(.trac-new):not(:has(.trac-field-attachment)) .changes").hide();
      // And only hide completely the changes which are not new, have no attachments and no comments
      $("div.change:not(.trac-new):not(:has(.trac-field-attachment)):not(:has(.comment))").hide();
    }
    changeCommentControlsVisibility();
  };

  // "Show comments" control
  var $show_comments = $("#trac-show-comments-toggle");
  var applyShowComments = function () {
    if ($show_comments.is(':checked'))
      $("#changelog .comment, #changelog .trac-lastedit").show();
    else
      $("#changelog .comment, #changelog .trac-lastedit").hide();
    changeCommentControlsVisibility();
  };

  // When neither the comments nor the change properties are visible,
  // it's hard to reach the change controls, so we make them always visible.
  var changeCommentControlsVisibility = function() {
    if (!$show_prop_changes.is(':checked') && !$show_comments.is(':checked')) {
      comment_controls_always_visible = true;
      $(".trac-ticket-buttons").css("visibility", "visible");
    } else if (comment_controls_always_visible) {
      comment_controls_always_visible = false;
      $(".trac-ticket-buttons").css("visibility", "hidden");
    }
  };

  // Only show the inline buttons for a change when hovered; note that
  // we have to cope with threaded comment mode, in which the
  // div.change are nested.
  $("#changelog").on("mouseenter mouseleave", "div.change", function(event) {
    if (comment_controls_always_visible)
      return;
    var enter = event.type == "mouseenter";
    $(".trac-ticket-buttons", $(this)).first().css("visibility",
                                                   enter ? "visible" : "hidden");
    $(this).parents("div.change").first()
      .find(".trac-ticket-buttons:first").css("visibility",
                                              enter ? "hidden" : "visible");
    if (enter)
      event.stopPropagation();
  });

  // "Oldest first", "Newest first", and "Threaded", the comments order controls
  var applyOrder = function() {
    var show_prop_changes_is_checked = $show_prop_changes.prop('checked');
    if (show_prop_changes_is_checked) {
      $show_prop_changes.prop("checked", false);
      applyShowPropertyChanges();
    }
    order = $("input[name='trac-comments-order']:checked").val();
    if (order == 'newest') {
      var $changelog = $("#changelog");
      $changelog.addClass("trac-most-recent-first");
      $changelog.append($("div.change").get().reverse());
    } else if (order == 'threaded') {
      comments = $("div.change");
      $(".trac-in-reply-to, .trac-follow-ups", comments).hide();
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
    if (order !== 'newest')
      $("#changelog").removeClass("trac-most-recent-first");
    if (show_prop_changes_is_checked) {
      $show_prop_changes.prop("checked", true);
      applyShowPropertyChanges();
    }
  };
  var unapplyOrder = function() {
    if (order == 'newest') {
      $("#changelog").append($("div.change").get().reverse());
    } else if (order == 'threaded') {
      if (comments.length) {
        $(".trac-in-reply-to, .trac-follow-ups", comments).show();
        var $changelog = $("#changelog");
        $changelog.append(comments);
        $("ul.children", $changelog).remove();
      }
    }
  };

  // Only propose "Threaded" if there are replies
  if ($("a.follow-up").length)
    $('#trac-threaded-toggle').show();
  else if (comments_prefs.comments_order == 'threaded')
    comments_prefs.comments_order = 'oldest';

  // Helper for saving preferences in user's session
  var savePrefs = function(key, value) {
    var data = {
      save_prefs: true,
      __FORM_TOKEN: form_token
    };
    data[key] = value;
    $.ajax({ url: form.attr('action'), type: 'POST', data: data, dataType: 'text' });
  };

  // Apply comments order preference
  var $trac_comments_order = $("input[name='trac-comments-order']");
  $trac_comments_order
    .filter("[value=" + comments_prefs.comments_order + "]")
    .prop('checked', true);
  applyOrder();
  $trac_comments_order.change(function() {
    unapplyOrder();
    applyOrder();
    savePrefs('ticket_comments_order', order);
  });

  // Apply "Show property changes" preference
  $show_prop_changes.prop('checked', comments_prefs.show_prop_changes == 'true');
  applyShowPropertyChanges();
  $show_prop_changes.click(function() {
    applyShowPropertyChanges();
    savePrefs('ticket_show_prop_changes', $show_prop_changes.is(':checked'));
  });

  // Apply "Show comments" preference
  $show_comments.prop('checked', comments_prefs.show_comments == 'true');
  applyShowComments();
  $show_comments.click(function () {
    applyShowComments();
    savePrefs('ticket_show_comments', $show_comments.is(':checked'));
  });
});
