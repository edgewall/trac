
(function($){
  
  // Convenience function for creating a <label>
  function createLabel(text, htmlFor) {
    var label = $($.htmlFormat("<label>$1</label>", text));
    if (htmlFor)
      label.attr("for", htmlFor).addClass("control");
    return label;
  }
  
  // Convenience function for creating an <input type="text">
  function createText(name, size) {
    return $($.htmlFormat('<input type="text" name="$1" size="$2">', 
                          name, size));
  }
  
  // Convenience function for creating an <input type="checkbox">
  function createCheckbox(name, value, id) {
    return $($.htmlFormat('<input type="checkbox" id="$1" name="$2"' +
                          ' value="$3">', id, name, value));
  }
  
  // Convenience function for creating an <input type="radio">
  function createRadio(name, value, id) {
    // Workaround for IE, otherwise the radio buttons are not selectable
    return $($.htmlFormat('<input type="radio" id="$1" name="$2"' +
                          ' value="$3">', id, name, value));
  }
  
  // Convenience function for creating a <select>
  function createSelect(name, options, optional) {
    var e = $($.htmlFormat('<select name="$1">', name));
    if (optional)
      $("<option>").appendTo(e);
    for (var i = 0; i < options.length; i++) {
      var opt = options[i], v = opt, t = opt;
      if (typeof opt == "object") 
        v = opt.value, t = opt.name;
      $($.htmlFormat('<option value="$1">$2</option>', v, t)).appendTo(e);
    }
    return e;
  }
  
  window.initializeFilters = function() {
    // Remove an existing row from the filters table
    function removeRow(button, propertyName) {
      var m = propertyName.match(/^(\d+)_(.*)$/);
      var clauseNum = m[1], field = m[2];
      var tr = $(button).closest("tr");
      
      // Keep the filter label when removing the first row
      var label = $("#label_" + propertyName);
      if (label.length && (label.closest("tr")[0] == tr[0])) {
        var next = tr.next("." + field);
        if (next.length) {
          var thisTh = tr.children().eq(1);
          var nextTh = next.children().eq(1);
          if (nextTh.attr("colSpan") == 1) {
            nextTh.replaceWith(thisTh);
          } else {
            nextTh.attr("colSpan", 1).before(thisTh);
            next.children().eq(2).replaceWith(tr.children().eq(1));
          }
        }
      }
      
      // Remove the row, filter tbody or clause tbody
      var tbody = tr.closest("tbody");
      if (tbody.children("tr").length > 1) {
        tr.remove();
      } else {
        var table = tbody.closest("table.trac-clause");
        var ctbody = table.closest("tbody");
        if (table.children().length > 2 || !ctbody.siblings().length) {
          tbody.remove();
          if (!ctbody.siblings().length && table.children().length == 1) {
            $("#add_clause").attr("disabled", true);
          }
        } else {
          var add_clause = $("#add_clause", ctbody);
          if (add_clause.length)
            $("tr.actions td.and", ctbody.prev()).attr("colSpan", 2)
              .after(add_clause.closest("td"));
          if (ctbody.prev().length == 0)
            ctbody.next().children("tr:first").attr("style", "display: none");
          ctbody.remove();
          return;
        }
      }
      
      // Re-enable non-multiline filter
      $("#add_filter_" + clauseNum + " option[value='" + field + "']")
        .enable();
    }
    
    // Make the submit buttons for removing filters client-side triggers
    $("#filters input[type='submit'][name^='rm_filter_']").each(function() {
      var idx = this.name.search(/_\d+$/);
      if (idx < 0)
        idx = this.name.length;
      var propertyName = this.name.substring(10, idx);
      $(this).replaceWith(
        $($.htmlFormat('<input type="button" value="$1">', this.value))
          .click(function() { 
                   removeRow(this, propertyName);
                   return false;
      }));
    });
    
    // Make the drop-down menu for adding a filter a client-side trigger
    $("#filters select[name^=add_filter_]").change(function() {
      if (this.selectedIndex < 1)
        return;

      if (this.options[this.selectedIndex].disabled) {
        // IE doesn't support disabled options
        alert(_("A filter already exists for that property"));
        this.selectedIndex = 0;
        return;
      }
      
      var propertyName = this.options[this.selectedIndex].value;
      var property = properties[propertyName];
      var table = $(this).closest("table.trac-clause")[0];
      var tbody = $("tr." + propertyName, table).closest("tbody").eq(0);
      var tr = $("<tr>").addClass(propertyName);
      
      var clauseNum = $(this).attr("name").split("_").pop();
      propertyName = clauseNum + "_" + propertyName;
      
      // Add the remove button
      tr.append($('<td>')
        .append($('<div class="inlinebuttons">')
          .append($('<input type="button" value="&ndash;">')
            .click(function() { removeRow(this, propertyName); }))));
      
      // Add the row header
      var th = $('<th scope="row">');
      if (!tbody.length) {
        th.append(createLabel(property.label)
                    .attr("id", "label_" + propertyName));
      } else {
        th.attr("colSpan", property.type == "time"? 1: 2)
          .append(createLabel(_("or")))
      }
      tr.append(th);
      
      var td = $("<td>");
      var focusElement = null;
      if (property.type == "radio" || property.type == "checkbox"
          || property.type == "time") {
        td.addClass("filter").attr("colSpan", 2);
        if (property.type == "radio") {
          for (var i = 0; i < property.options.length; i++) {
            var option = property.options[i];
            td.append(createCheckbox(propertyName, option, 
                                     propertyName + "_" + option)).append(" ")
              .append(createLabel(option ? option : "none",
                                  propertyName + "_" + option)).append(" ");
          }
        } else if (property.type == "checkbox") {
          td.append(createRadio(propertyName, "1", propertyName + "_on"))
            .append(" ").append(createLabel(_("yes"), propertyName + "_on"))
            .append(" ")
            .append(createRadio(propertyName, "0", propertyName + "_off"))
            .append(" ").append(createLabel(_("no"), propertyName + "_off"));
        } else if (property.type == "time") {
          focusElement = createText(propertyName, 14)
          td.append(createLabel(_("between"))).append(" ")
            .append(focusElement).append(" ")
            .append(createLabel(_("and"))).append(" ")
            .append(createText(propertyName + "_end", 14));
        }
        tr.append(td);
      } else {
        if (!tbody.length) {
          // Add the mode selector
          td.addClass("mode")
            .append(createSelect(propertyName + "_mode", modes[property.type]))
            .appendTo(tr);
        }
        
        // Add the selector or text input for the actual filter value
        td = $("<td>").addClass("filter");
        if (property.type == "select") {
          focusElement = createSelect(propertyName, property.options, true);
        } else if ((property.type == "text") || (property.type == "id")
                   || (property.type == "textarea")) {
          focusElement = createText(propertyName, 42);
        }
        td.append(focusElement).appendTo(tr);
      }
      
      if (!tbody.length) {
        tbody = $("<tbody>");
        
        // Find the insertion point for the new row. We try to keep the filter
        // rows in the same order as the options in the 'Add filter' drop-down,
        // because that's the order they'll appear in when submitted
        var insertionPoint = $(this).closest("tbody");
        outer:
        for (var i = this.selectedIndex + 1; i < this.options.length; i++) {
          for (var j = 0; j < table.tBodies.length; j++) {
            if (table.tBodies[j].rows[0].className == this.options[i].value) {
              insertionPoint = $(table.tBodies[j]);
              break outer;
            }
          }
        }
        insertionPoint.before(tbody);
      }
      tbody.append(tr);
      
      if(focusElement)
          focusElement.focus();
      
      // Disable the add filter in the drop-down list
      if (property.type == "radio" || property.type == "checkbox"
          || property.type == "id")
        this.options[this.selectedIndex].disabled = true;
      
      this.selectedIndex = 0;

      // Enable the Or... button if it's been disabled
      $("#add_clause").attr("disabled", false);
    }).next("div.inlinebuttons").remove();
    
    // Add a new empty clause at the end by cloning the current last clause
    function addClause(select) {
      var tbody = $(select).closest("tbody");
      var clauseNum = parseInt($(select).attr("name").split("_").pop());
      var tbody = $(select).closest("tbody").parents("tbody").eq(0);
      var copy = tbody.clone(true);
      $(select).closest("td").next().attr("colSpan", 4).end().remove();
      $("tr:first", copy).removeAttr("style");
      $("tr tbody:not(:last)", copy).remove();
      var newId = "add_filter_" + clauseNum;
      $("select[name^=add_filter_]", copy).attr("id", newId)
        .attr("name", newId)
        .children().enable().end()
        .prev().attr("for", newId);
      $("select[name^=add_clause_]", copy)
        .attr("name", "add_clause_" + (clauseNum + 1));
      tbody.after(copy);
    }
    
    var add_clause = $("#add_clause");
    add_clause.change(function() {
      // Add a new clause and fire a change event on the new clause's
      // add_filter select.
      var field = $(this).val();
      addClause(this);
      $("#add_clause").closest("tr").find("select[name^=add_filter_]")
        .val(field).change();
    }).next("div.inlinebuttons").remove();
    if (!add_clause.closest("tbody").siblings().length) {
      // That is, if there are no filters added to this clause
      add_clause.attr("disabled", true);
    }
  }
  
  window.initializeBatch = function(){
  	//Create the appropriate input for the property.
    function createBatchInput(inputName, property){
        var td = $('<td class="batchmod_property">');
        switch(property.type){
            case 'select':
                td.append(createSelect(inputName, property.options, true));
                break;
            case 'radio':
                for (var i = 0; i < property.options.length; i++) {
                    var option = property.options[i];
                    td.append(createRadio(inputName, option, inputName + "_" + option))
                        .append(" ")
                        .append(createLabel(option ? option : "none", inputName + "_" + option))
                        .append(" ");
                }
                break;
            case 'checkbox':
                td.append(createRadio(inputName, "1", inputName + "_on"))
                    .append(" ").append(createLabel(_("yes"), inputName + "_on"))
                    .append(" ")
                    .append(createRadio(inputName, "0", inputName + "_off"))
                    .append(" ").append(createLabel(_("no"), inputName + "_off"));
                break;
            case 'text':
                td.append(createText(inputName, 42));
                break;
            case 'time':
                td.append(createText(inputName, 42).addClass("time"));
                break;
        }
        return td;
    }
    
    function getBatchInputName(propertyName){
        return 'batchmod_value_' + propertyName;
    }

    function getDisabledBatchOptions(){
        return $("#add_batchmod_field option:disabled");
    }
    
    //Add a new column with checkboxes for each ticket.
    //Selecting a ticket marks it for inclusion in the batch. 
    $("table.listing tr td.id").each(function() {
        tId=$(this).text().substring(1); 
        $(this).before('<td><input type="checkbox" name="selected_ticket" class="batchmod_selector" value="'+tId+'"/></td>');
    });

    //Add a checkbox at the top of the column to select ever ticket in the group.
    $("table.listing tr th.id").each(function() { 
        $(this).before('<th class="batchmod_selector"><input type="checkbox" name="batchmod_toggleGroup" /></th>');
    });

    //Add the click behavior for the group toggle. 
    $("input[name='batchmod_toggleGroup']").click(function() { 
        $("tr td input.batchmod_selector",$(this).parents("table.listing")).attr("checked",this.checked);
    });
  
    //At least one ticket must be selected to submit the batch.
    $("form#batchmod_form").submit(function() {
        //First remove all existing validation messages.
        $(".batchmod_required").remove();
        
        var valid = true;
        var selectedTix=[];    
        $("input[name=selected_ticket]:checked").each( function(){ selectedTix.push(this.value);} ); 
        $("input[name=selected_tickets]").val(selectedTix);
        
        //At least one ticket must be selected.
        if(selectedTix.length === 0){
            $("#batchmod_submit").after('<span class="batchmod_required">You must select at least one ticket.</span>');
            valid = false;
        }
        
        //Check that each radio property has something selected.
        getDisabledBatchOptions().each(function(){
            var propertyName = $(this).val();
            if(properties[propertyName].type == "radio"){
                var isChecked = false;
                var inputName = getBatchInputName(propertyName);
                $("[name=" + inputName + "]").each(function(){
                    isChecked = isChecked || $(this).is(':checked');
                });
                if(!isChecked){
                    //Select the last label in the row to add the error message
                    $("[name=" + inputName + "] ~ label:last")
                        .after('<span class="batchmod_required">Required</span>');
                    valid = false;
                }
            }
        });
        
        //If the status is set to closed, a resolution must be selected.
        if($("#batchmod_value_status_closed").checked() && $("#batchmod_resolution").length < 1){
            $("[name=batchmod_value_status] ~ label:last").after('<span class="batchmod_required">Resolution Required</span>');
            valid = false;
        }
        
        return valid;
    });
  
    //Collapse the form by default
    $("#batchmod_fieldset").toggleClass("collapsed");
  
    //Add the new batch modify field when the user selects one from the dropdown.
    $("#add_batchmod_field").change(function() {
        if (this.selectedIndex < 1){
            return;
        }
        
        //Trac has a properties object that has information about each property that filters
        //could be built with. We use it hear to add batchmod fields.
        var propertyName = this.options[this.selectedIndex].value;
        var property = properties[propertyName];
        
        var tr = $("<tr>").attr('id', 'batchmod_' + propertyName);
        
        // Add the remove button
        tr.append($('<td>')
            .append($('<div class="inlinebuttons">')
                .append($('<input type="button" value="&ndash;">')
                    .click(function() { 
                        $('#batchmod_' + propertyName).remove();
                        $($.htmlFormat("#add_batchmod_field option[value='$1']", propertyName)).enable(); 
                    })
                )
            )
        );
        
        //Add the header row.
        tr.append($('<th scope="row">')
            .append(createLabel(property.label, getBatchInputName(propertyName)))
        );
        
        // Add the input element.
        tr.append(createBatchInput(getBatchInputName(propertyName), property));
        
        //New rows are added in the same order as listed in the dropdown. This is the same behavior as the filters.
        var insertionPoint = null;
        getDisabledBatchOptions().each(function(){
            if(insertionPoint === null && $(this).val() > propertyName){
                insertionPoint = $("#batchmod_" + $(this).val());
            }
            
        });
        if (insertionPoint === null) {
            insertionPoint = $("#batchmod_comment");
        }
        insertionPoint.before(tr);
        
        //Disable each element from the option list when it is selected.
        this.options[this.selectedIndex].disabled = 'disabled';
    });
  }

})(jQuery);
