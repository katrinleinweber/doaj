jQuery(document).ready(function($) {

    // define a new highlight function, letting us highlight any element
    // on a page
    // adapted from http://stackoverflow.com/a/11589350
    jQuery.fn.highlight = function(color, fade_time) {
       // some defaults
       var color = color || "#F68B1F";  // the DOAJ color
       var fade_time = fade_time || 1500;  // milliseconds

       $(this).each(function() {
            var el = $(this);
            el.before("<div/>")
            el.prev()
                .width(el.width())
                .height(el.height())
                .css({
                    "position": "absolute",
                    "background-color": color,
                    "opacity": ".9"   
                })
                .fadeOut(fade_time);
        });
    }

    // animated scrolling to an anchor
    jQuery.fn.anchorAnimate = function(settings) {

        settings = jQuery.extend({
            speed : 700
        }, settings);   
    
        return this.each(function(){
            var caller = this
            $(caller).click(function (event) {  
                event.preventDefault()
                var locationHref = window.location.href
                var elementClick = $(caller).attr("href")
    
                var destination = $(elementClick).offset().top;

                $("html:not(:animated),body:not(:animated)").animate({ scrollTop: destination}, settings.speed, function() {
                    window.location.hash = elementClick;  // ... but it also needs to be getting set here for the animation itself to work
                });

                setTimeout(function(){
                    highlight_target();
                }, settings.speed + 50);

                return false;
            })
        })
    }

    $("#submit_status").click(function(event) {
        event.preventDefault()
        
        var newstatus = $("select[name=application_status]").val()
        var suggestion_id = $("input[name=suggestion_id]").val()
        var original = $("input[name=current_status]").val()
        var obj = {"status" : newstatus}
        
        $.ajax({
            type: "POST",
            url: "/admin/suggestion/" + suggestion_id,
            contentType: "application/json",
            dataType: "json",
            data: JSON.stringify(obj),
            success: function() {
                // alert("status updated")
                // update the hidden field
                $("input[name=current_status]").val(newstatus)
                $("#submit_status").attr("disabled", "disabled")
                $("#submit_status").attr("class", "btn")
            },
            error: function() {
                alert("ERROR: unable to update status.  If the problem persists, please contact your sysadmin.")
                // reset the pull-down
                $("select[name=application_status] option").filter(function() {return $(this).val() === original}).prop("selected", true)
                $("#submit_status").attr("disabled", "disabled")
                $("#submit_status").attr("class", "btn")
            },
            complete: function(req, status) {
                // alert(status)
            }
        })

    });
    
    $("select[name=application_status]").change(function() {
        var original = $("input[name=current_status]").val()
        var newstatus = $("select[name=application_status]").val()
        
        if (newstatus !== original) {
            $("#submit_status").removeAttr("disabled")
            $("#submit_status").attr("class", "btn btn-info")
        } else {
            $("#submit_status").attr("disabled", "disabled")
            $("#submit_status").attr("class", "btn")
        }
    });
    
    
    toggle_optional_field('waiver_policy', ['#waiver_policy_url']);
    toggle_optional_field('download_statistics', ['#download_statistics_url']);
    toggle_optional_field('plagiarism_screening', ['#plagiarism_screening_url']);
    toggle_optional_field('publishing_rights', ['#publishing_rights_url'], ["True", "Other"]);
    toggle_optional_field('copyright', ['#copyright_url'], ["True", "Other"]);
    toggle_optional_field('license_embedded', ['#license_embedded_url']);
    toggle_optional_field('processing_charges', ['#processing_charges_amount', '#processing_charges_currency']);
    toggle_optional_field('submission_charges', ['#submission_charges_amount', '#submission_charges_currency']);
    toggle_optional_field('license', ['#license_checkbox'], ["Other"]);
    toggle_optional_field('license', ['#license_url'], ['cc-by', 'cc-by-sa', 'cc-by-nc', 'cc-by-nd', 'cc-by-nc-nd', "Other"]);
    
    $('#country').select2();
    $('#processing_charges_currency').select2();
    $('#submission_charges_currency').select2();
    
    $("#keywords").select2({
        minimumInputLength: 1,
        tags: [],
        tokenSeparators: [","],
        maximumSelectionSize: 6
    });
    
    $("#languages").select2();
          
    autocomplete('#publisher', 'bibjson.publisher');
    autocomplete('#society_institution', 'bibjson.institution');
    autocomplete('#platform', 'bibjson.provider');

    exclusive_checkbox('digital_archiving_policy', 'No policy in place');
    exclusive_checkbox('article_identifiers', 'None');
    exclusive_checkbox('deposit_policy', 'None');
    
    if ("onhashchange" in window) {
        window.onhashchange = highlight_target();
        $('a.animated').anchorAnimate();
    }
});

function toggle_optional_field(field_name, optional_field_selectors, values_to_show_for) {
    var values_to_show_for = values_to_show_for || ["True"];
    var main_field_selector = 'input[name=' + field_name + '][type="radio"]';

    // hide all optional fields first
    for (var i = 0; i < optional_field_selectors.length; i++) {
        $(optional_field_selectors[i]).parents('.control-group').hide();
    }

    // show them again if the correct radio button is chosen
    $(main_field_selector).each( function () {
        __init_optional_field(this, optional_field_selectors, values_to_show_for);
    });

    $(main_field_selector).change( function () {
        if ($.inArray(this.value, values_to_show_for) >= 0) {
            for (var i = 0; i < optional_field_selectors.length; i++) {
                $(optional_field_selectors[i]).parents('.control-group').show();
            }
        } else {
            for (var i = 0; i < optional_field_selectors.length; i++) {
                $(optional_field_selectors[i]).parents('.control-group').hide();
            }
        }
    });
}

function __init_optional_field(elem, optional_field_selectors, values_to_show_for) {
    var values_to_show_for = values_to_show_for || ["True"];
    var main_field = $(elem);

    if (main_field.is(':checked') && $.inArray(main_field.val(), values_to_show_for) >= 0) {
        for (var i = 0; i < optional_field_selectors.length; i++) {
            $(optional_field_selectors[i]).parents('.control-group').show();
        }
    }
}

function autocomplete(selector, doc_field, doc_type) {
    var doc_type = doc_type || "journal";
    $(selector).select2({
        minimumInputLength: 3,
        ajax: {
            url: "../autocomplete/" + doc_type + "/" + doc_field,
            dataType: 'json',
            data: function (term, page) {
                return {
                    q: term
                };
            },
            results: function (data, page) {
                return { results: data["suggestions"] };
            }
        },
        createSearchChoice: function(term) {return {"id":term, "text": term};}
    });
}

function exclusive_checkbox(field_name, exclusive_val) {
    $('#' + field_name + ' :checkbox[value="' + exclusive_val + '"]').change(function() {
        if (this.checked) {
            $('#' + field_name + ' :checkbox:not([value="' + exclusive_val + '"])').prop('disabled', true);
            $('#' + field_name + ' .extra_input_field').prop('disabled', true);
        } else {
            $('#' + field_name + ' :checkbox:not([value="' + exclusive_val + '"])').prop('disabled', false);
            $('#' + field_name + ' .extra_input_field').prop('disabled', false);
        }
    });
}

function highlight_target() {
    console.log(window.location.hash);
    $(window.location.hash).highlight()
}
