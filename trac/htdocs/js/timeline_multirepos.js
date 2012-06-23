jQuery(document).ready(function($){
  var csetfilter = $("input[name=changeset]");
  function toggleRepositories() {
    $("input[name^=repo-]").attr("checked", csetfilter.checked());
  }
  csetfilter.click(toggleRepositories);
  toggleRepositories();
});
