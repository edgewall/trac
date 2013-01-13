// Allow resizing <textarea> elements through a drag bar

jQuery(document).ready(function($) {
  $('textarea.trac-resizable').each(function() {
    var textarea = $(this);
    var offset = null;

    function beginDrag(e) {
      offset = textarea.height() - e.pageY;
      textarea.blur();
      $(document).mousemove(dragging).mouseup(endDrag);
      return false;
    }

    function dragging(e) {
      textarea.height(Math.max(32, offset + e.pageY) + 'px');
      return false;
    }

    function endDrag(e) {
      textarea.focus();
      $(document).unbind('mousemove', dragging).unbind('mouseup', endDrag);
    }

    var grip = $('<div class="trac-grip"/>').mousedown(beginDrag)[0];
    textarea.wrap('<div class="trac-resizable"><div></div></div>')
            .parent().append(grip);
    grip.style.marginLeft = (this.offsetLeft - grip.offsetLeft) + 'px';
    grip.style.marginRight = (grip.offsetWidth - this.offsetWidth) +'px';
  });
});
