jQuery(document).ready(function ($) {
  var $enumtable = $('#enumtable');
  var $enumlist = $('#enumlist', $enumtable);
  var $apply_button = $('input[name="apply"]', $enumtable);

  $enumlist.addSelectAllCheckboxes();

  // Insert 'Revert changes' button after the 'Apply changes' button
  var $revert_button = $('<input type="submit" name="revert" value="Revert changes" disabled="disabled" />')
                       .insertAfter($apply_button);

  // Disable the 'Apply changes' button until there is a change
  $apply_button.prop('disabled', true);
  $enumtable.find('input:radio').click(function () {
    $apply_button.prop('disabled', false);
    $revert_button.prop('disabled', false);
  });

  // Don't prompt with a dialog if the 'Apply/Revert changes' button is pressed
  var button_pressed;
  $enumtable.find('div.buttons input').click(function () {
    button_pressed = $(this).attr('name');
  });

  $enumtable.submit(function () {
    if (button_pressed === 'apply' || button_pressed === 'revert') {
      $(window).unbind('beforeunload');
    }
    if (button_pressed === 'revert') {
      // Send GET request instead of POST
      location = location;
      return false;
    }
  });

  // Initialize items as sortable
  $enumlist.find('tbody').sortable({
    axis: 'y',
    cursor: 'move',
    containment: $enumlist,
    tolerance: 'pointer',
    start: function (event, ui) {
      // Keep column widths of dragged items equal to header.
      var $tds = ui.item.children();
      var $ths = $('thead th', $enumlist);
      $ths.each(function (idx) {
        $tds.eq(idx).css('width', $(this).width() + 'px');
      });
    },
    stop: function (event, ui) {
      updateValues(ui.item)
    }
  });

  // When user changes a select value, reorder rows
  $enumlist.find('select').change(function () {
    // Move ($this) in the right position
    var $tr = $(this).closest('tr');
    var val = $(this).val();
    if (val == 1) {
      $enumlist.find('tbody').prepend($tr);
    } else {
      var row_index = 0;
      var sib = $tr.prev();
      while (sib.length != 0) {
        row_index++;
        sib = sib.prev();
      }
      var new_index = val > row_index ? val : val - 1;
      $('tr', $enumlist).eq(new_index).after($tr);
    }
    updateValues($tr);
  });

  // Set select values based their row and highlight those changed.
  function updateValues($tr) {
    var unsaved_changes = false;
    var position = 1;
    var $tr_select = $('select', $tr);
    $enumlist.find('select').each(function () {
      var $select = $(this);
      var val = $select.val();
      var $parent = $select.closest('tr');
      $parent.stop(true, true);
      if (val != position || val === $tr_select.val()) {
        $parent.effect('highlight', {color: '#ffb'}, 3000);
        $select.val(position);
        unsaved_changes = true;
      }
      position += 1;
    });

    if (unsaved_changes) {
      $.setWarningUnsavedChanges(true);
      $revert_button.prop('disabled', false);
      $apply_button.prop('disabled', false);
    }
  }
});
