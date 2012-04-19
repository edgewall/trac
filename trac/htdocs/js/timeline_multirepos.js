jQuery(document).ready(function($){
  var csetfilter = $("input[name=changeset]");
  function toggleRepositories() {
    $("input[name^=repo-]").parent().toggle();
  }
  csetfilter.click(toggleRepositories);
  if (csetfilter.checked()) 
    toggleRepositories();
});
