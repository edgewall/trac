jQuery(function($){
  // TRANSLATOR: Format in month heading in the datepicker, extracts yearSuffix
  // and showMonthAfterYear
  var formatMonth = _("$month$year");
  $.datepicker.setDefaults({
    // TRANSLATOR: Link that closes the datepicker
    closeText: _("Done"),
    // TRANSLATOR: Link to the previous month in the datepicker
    prevText: _("Prev"),
    // TRANSLATOR: Link to the next month in the datepicker
    nextText: _("Next"),
    // TRANSLATOR: Link to the current day in the datepicker
    currentText: _("Today"),
    monthNames: jquery_ui.month_names.wide,
    monthNamesShort: jquery_ui.month_names.abbreviated,
    dayNames: jquery_ui.day_names.wide,
    dayNamesShort: jquery_ui.day_names.abbreviated,
    dayNamesMin: jquery_ui.day_names.narrow,
    // TRANSLATOR: Heading for the week-of-the-year column in the datepicker
    weekHeader: _("Wk"),
    yearSuffix: $.format(formatMonth, {month: '', year: ''}),
    dateFormat: jquery_ui.date_format,
    firstDay: jquery_ui.first_week_day,
    isRTL: false,
    showMonthAfterYear: formatMonth.indexOf('$month') >
                        formatMonth.indexOf('$year')
  });
  $.timepicker.setDefaults({
    // TRANSLATOR: Heading of the standalone timepicker
    timeOnlyTitle: _("Choose Time"),
    // TRANSLATOR: Time selector label
    timeText: _("Time"),
    // TRANSLATOR: Time labels in the timepicker
    hourText: _("Hour"), minuteText: _("Minute"), secondText: _("Second"),
    timezoneText: _("Time Zone"),
    // TRANSLATOR: Link to pick the current time in the timepicker
    currentText: _("Now"),
    // TRANSLATOR: Link that closes the timepicker
    closeText: _("Done"),
    timeFormat: jquery_ui.time_format,
    separator: jquery_ui.timepicker_separator,
    timezone: 'Z',
    showTimezone: jquery_ui.show_timezone,
    timezoneList: jquery_ui.timezone_list,
    timezoneIso8601: jquery_ui.timezone_iso8601,
    ampm: jquery_ui.ampm,
    showSecond: true
  });
});
