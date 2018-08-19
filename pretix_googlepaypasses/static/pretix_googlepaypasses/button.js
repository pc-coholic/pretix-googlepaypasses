$(function() {
  $('#googlepaypassesmodal .modal-dialog').each(function() {
    // .modal-backdrop has a z-index of 1040
    // .modal has a z-index of 1050
    // Yet, this modal is shown underneath the backdrop. Not sure, if this bug
    // is pretix, bootstrap or - more probably - plugin related.
    $(this).css('z-index', 1060);
  });

  $('a[href*="googlepaypasses"]').click(function(event) {
    event.preventDefault();
    $('#googlepaypassesmodal .btn-primary').attr('href', $(this).attr('href') + '/generate');
    $('#googlepaypassesmodal').modal('toggle');
    return false;
  });
});
