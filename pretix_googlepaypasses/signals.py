from collections import OrderedDict

from django import forms
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _
from pretix.base.signals import (
    register_global_settings, register_ticket_outputs,
)

from .forms import validate_json_credentials


@receiver(register_ticket_outputs, dispatch_uid='output_googlepaypasses')
def register_ticket_output(sender, **kwargs):
    from .googlepaypasses import WalletobjectOutput
    return WalletobjectOutput


@receiver(register_global_settings, dispatch_uid='googlepaypasses_settings')
def register_global_settings(sender, **kwargs):
    return OrderedDict([
        ('googlepaypasses_issuer_id', forms.CharField(
            label=_('Google Pay Passes Issuer/Merchant ID'),
            help_text=_('After getting accepted by Google into the Google Pay API for Passes program, '
                        'your Issuer ID can be found in the Merchant center at '
                        'https://wallet.google.com/merchant/walletobjects/'),
            required=False,
        )),
        ('googlepaypasses_credentials', forms.CharField(
            label=_('Google Pay Passes Service Account Credentials'),
            help_text=_('Please paste the contents of the JSON credentials file '
                        'of the service account you tied to your Google Pay API '
                        'for Passes Issuer ID'),
            required=False,
            widget=forms.Textarea,
            validators=[validate_json_credentials]
        )),
        ('passbook_gmaps_api_key', forms.CharField(
            label=_('Google Maps API key'),
            widget=forms.PasswordInput(render_value=True),
            required=False,
            help_text=_('Optional, only necessary to find coordinates automatically.')
        )),
    ])
