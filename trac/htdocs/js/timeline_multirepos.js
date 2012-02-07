jQuery(document).ready(function($){
  csetfilter = $("input[name=changeset]");
  function toggleRepositories() {
    $("input[name^=repo-]").attr("checked", csetfilter.checked());
  }
  csetfilter.click(toggleRepositories);
  toggleRepositories();
});
