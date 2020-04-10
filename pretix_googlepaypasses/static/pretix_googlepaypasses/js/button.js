$(function() {
  if (!$('#googlepaypassesmodal .modal-dialog').length) {
    return;
  }

  $('#googlepaypassesmodal .modal-dialog').each(function() {
    // .modal-backdrop has a z-index of 1040
    // .modal has a z-index of 1050
    // Yet, this modal is shown underneath the backdrop. Not sure, if this bug
    // is pretix, bootstrap or - more probably - plugin related.
    $(this).css('z-index', 1060);
  });

  $('form[action*="googlepaypasses"]').click(function(event) {
    event.preventDefault();
    $('#googlepaypassesmodal form').attr('action', $(this).attr('action'));
    $('#googlepaypassesmodal form input[name=csrfmiddlewaretoken]').attr('value', $('input[name=csrfmiddlewaretoken]:last').val());
    $('#googlepaypassesmodal').modal('toggle');
    return false;
  });
});
