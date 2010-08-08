jQuery(document).ready(function($){
    // Convenience function for creating a <label>
    function createLabel(text, htmlFor) {
        var label = $($.htmlFormat("<label>$1</label>", text));
        if (htmlFor) {
            label.attr("for", htmlFor).addClass("control");
        }
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
        var e = $($.htmlFormat('<select id="$1" name="$1">', name));
        if (optional) {
            $("<option>").appendTo(e);
        }
        for (var i = 0; i < options.length; i++) {
            var opt = options[i], v = opt, t = opt;
            if (typeof opt == "object") {
                v = opt.value;
                t = opt.text;
            }
            $($.htmlFormat('<option value="$1">$2</option>', v, t)).appendTo(e);
        }
        return e;
    }
    
    //Create the appropriate input for the property.
    function createInput(inputName, property){
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
    
    function getInputName(propertyName){
        return 'batchmod_value_' + propertyName;
    }

    function getDisabledOptions(){
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
        getDisabledOptions().each(function(){
            var propertyName = $(this).val();
            if(properties[propertyName].type == "radio"){
                var isChecked = false;
                var inputName = getInputName(propertyName);
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
            .append(createLabel(property.label, getInputName(propertyName)))
        );
        
        // Add the input element.
        tr.append(createInput(getInputName(propertyName), property));
        
        //New rows are added in the same order as listed in the dropdown. This is the same behavior as the filters.
        var insertionPoint = null;
        getDisabledOptions().each(function(){
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
});