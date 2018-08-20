from collections import OrderedDict
import json

from django import forms
from django.dispatch import receiver
from django.urls import resolve
from django.utils.translation import ugettext_lazy as _
from django.template.loader import get_template
from pretix.base.signals import (
    register_global_settings, register_ticket_outputs,
)
from pretix.presale.signals import html_head as html_head_presale
from django.db.models.signals import post_save
from pretix.base.models import LogEntry, OrderPosition

from pretix_googlepaypasses.googlepaypasses import WalletobjectOutput

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

@receiver(html_head_presale, dispatch_uid="googlepaypasses_html_head_presale")
def html_head_presale(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    print(url.func.__name__)
    if url.namespace == 'presale' and url.func.__name__ == 'OrderDetails':
        template = get_template('pretix_googlepaypasses/presale_head.html')
        return template.render({})
    else:
        return ""

@receiver(post_save, sender=LogEntry, dispatch_uid="googlepaypasses_logentry_post_save")
def logentry_post_save(sender, instance, **kwargs):
    if instance.action_type in ['pretix.event.order.secret.changed', 'pretix.event.order.changed.secret']:
        instanceData = json.loads(instance.data)

        if 'position' and 'positionid' in instanceData:
            # {"position": 4, "positionid": 1} --> changed OrderPosition
            op = OrderPosition.objects.get(order=instance.object_id, id=instanceData['position'])
            WalletobjectOutput.shredEventTicketObject(op, WalletobjectOutput.getAuthedSession(op.order.event.settings))
        else:
            # {} --> whole changed Order
            ops = OrderPosition.objects.filter(order=instance.object_id)
            for op in ops:
                WalletobjectOutput.shredEventTicketObject(op, WalletobjectOutput.getAuthedSession(op.order.event.settings))
