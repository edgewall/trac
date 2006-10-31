$.fn.enableFolding = function(expr) {
  var fragId = document.location.hash;
  if (fragId && /^#no\d+$/.test(fragId)) {
    fragId = parseInt(fragId.substr(3));
  }

  var count = 1;
  return this.each(function() {
    var trigger = this;
    $(this).wrap("<a href='#no" + count + "'></a>").parent().click(function() {
      if (fragId == count) { fragId = 0; return; }
      $(this.parentNode).toggleClass("collapsed");
    }).click();
    count++;
  }).css("cursor", "pointer");
}
