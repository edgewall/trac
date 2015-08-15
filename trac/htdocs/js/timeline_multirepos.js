jQuery(document).ready(function($){
  var $cset_filter = $("input[name=changeset]");
  var $repo_list = $("input[name^=repo-]");
  var show_message = _("Show all repositories");
  var hide_message = _("Hide all repositories");

  function toggleExpander() {
    $repo_list.parent().toggle();
    if ($($repo_list[0]).is(":visible")) {
      $repolist_expander.addClass("expanded").prop("title", hide_message);
    }
    else {
      $repolist_expander.removeClass("expanded").prop("title", show_message);
    }
    return false; //prohibit checkbox toggling
  }

  // Set tri-state changeset checkbox.
  function updateChangesetFilter() {
    var total_checked = $repo_list.filter(":checked").length;
    var none_selected = total_checked === 0;
    var all_selected = total_checked === $repo_list.length;
    $cset_filter.prop({
      "checked": all_selected,
      "indeterminate": !(none_selected || all_selected)
    });
  }

  // Show/hide all repositories.
  var $repolist_expander = $("<span />", {
    "class": "expander",
    "title": show_message
  }).click(toggleExpander);

  // Check/uncheck all repositories.
  $cset_filter.click(function() {
    $repo_list.prop("checked", this.checked);
  }).keydown(function(e) {
    // L and R arrow keys toggle expander
    if (e.which == 37 || e.which == 39) {
        toggleExpander();
    }
  }).after($repolist_expander);

  $repo_list.click(function() {
    updateChangesetFilter();
  });

  // Initial display.
  $repo_list.parent().hide();
  updateChangesetFilter();
});
