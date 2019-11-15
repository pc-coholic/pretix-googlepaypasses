import json
from collections import OrderedDict

from django import forms
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import resolve
from django.utils.translation import ugettext_lazy as _
from pretix.base.models import Event, LogEntry, OrderPosition
from pretix.base.signals import (
    periodic_task, register_global_settings, register_ticket_outputs,
    requiredaction_display,
)
from pretix.presale.signals import html_head as html_head_presale
from pretix_googlepaypasses.googlepaypasses import WalletobjectOutput
from .import tasks

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

    if url.namespace == 'presale' and url.func.__name__ in ['OrderDetails', 'OrderPositionDetails']:
        template = get_template('pretix_googlepaypasses/presale_head.html')
        return template.render({})
    else:
        return ""


@receiver(post_save, sender=LogEntry, dispatch_uid="googlepaypasses_logentry_post_save")
def logentry_post_save(sender, instance, **kwargs):
    if instance.action_type in [
        'pretix.event.order.secret.changed', 'pretix.event.order.changed.secret', 'pretix.event.order.changed.cancel',
        'pretix.event.order.changed.split'
    ]:
        instanceData = json.loads(instance.data)

        if 'position' and 'positionid' in instanceData:
            # {"position": 4, "positionid": 1} --> changed OrderPosition
            op = OrderPosition.objects.get(order=instance.object_id, id=instanceData['position'])
            tasks.shredEventTicketObject.apply_async(args=(op.id,))
        else:
            # {} --> whole changed Order
            ops = OrderPosition.objects.filter(order=instance.object_id)
            for op in ops:
                tasks.shredEventTicketObject.apply_async(args=(op.id,))
    elif instance.action_type in ['pretix.event.order.changed.item', 'pretix.event.order.changed.price', 'pretix.event.order.changed.subevent']:
        instanceData = json.loads(instance.data)
        op = OrderPosition.objects.get(order=instance.object_id, id=instanceData['position'])

        tasks.generateEventTicketObjectIfExisting.apply_async(args=(op.id,))
    elif instance.action_type in ['pretix.event.tickets.provider.googlepaypasses', 'pretix.event.changed', 'pretix.event.settings']:
        event = Event.objects.get(id=instance.event_id)

        tasks.generateEventTicketClassIfExisting.apply_async(args=(event.id,))
    elif instance.action_type in ['pretix.organizer.settings']:
        events = Event.objects.filter(organizer_id=instance.object_id, plugins__contains='pretix_googlepaypasses')

        for event in events:
            tasks.generateEventTicketClassIfExisting.apply_async(args=(event.id))


@receiver(signal=requiredaction_display, dispatch_uid="googlepaypasses_requiredaction_display")
def pretixcontrol_action_display(sender, action, request, **kwargs):
    if not action.action_type.startswith('pretix_googlepaypasses'):
        return

    data = json.loads(action.data)

    if action.action_type == 'pretix_googlepaypasses.evenTicketClassFail':
        template = get_template('pretix_googlepaypasses/action_evenTicketClassFail.html')
    elif action.action_type == 'pretix_googlepaypasses.evenTicketObjectFail':
        template = get_template('pretix_googlepaypasses/action_evenTicketObjectFail.html')

    ctx = {'data': data, 'event': sender, 'action': action}
    return template.render(ctx, request)


@receiver(signal=periodic_task)
def shred_unused_objects(sender, **kwargs):
    # Oh well...
    # Google does supposedly report if a WalletObject has any users...
    #
    # hasUsers - boolean - Indicates if the object has users. This field is set by the platform
    #
    # Guess, what, it doesn't work and reports "hasUsers -> False" even when the object is installed.
    # Perhaps this is just a timing issue (Result is cached on the Google-side?) - but for now we cannot
    # offer automatic shredding of unused passes. Sucks :-(
    return

    ops = OrderPosition.objects.filter(meta_info__contains='"googlepaypass"')
    for op in ops:
        authedSession = WalletobjectOutput.getAuthedSession(op.order.event.settings)
        meta_info = json.loads(op.meta_info or '{}')
        evTobjectID = meta_info['googlepaypass']

        evTobject = WalletobjectOutput.getEventTicketObjectFromServer(evTobjectID, authedSession)

        if not evTobject['hasUsers']:
            WalletobjectOutput.shredEventTicketObject(op, authedSession)
