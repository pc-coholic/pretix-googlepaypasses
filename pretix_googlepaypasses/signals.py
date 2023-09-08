import json
from collections import OrderedDict

from django import forms
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import resolve
from django.utils.translation import gettext_lazy as _, gettext_noop
from i18nfield.strings import LazyI18nString
from pretix.base.models import Event, LogEntry, OrderPosition
from pretix.base.settings import settings_hierarkey
from pretix.base.signals import (
    periodic_task, register_global_settings, register_ticket_outputs,
)
from pretix.presale.signals import html_head as html_head_presale
from pretix_googlepaypasses import tasks
from pretix_googlepaypasses.forms import validate_json_credentials


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
    ])


@receiver(html_head_presale, dispatch_uid="googlepaypasses_html_head_presale")
def html_head_presale(sender, request=None, **kwargs):
    url = resolve(request.path_info)

    if url.namespace == 'presale' and url.func.__name__ in ['OrderDetails', 'OrderPositionDetails']:
        template = get_template('pretix_googlepaypasses/presale_head.html')
        return template.render({'event': sender})
    else:
        return ""


@receiver(post_save, sender=LogEntry, dispatch_uid="googlepaypasses_logentry_post_save")
def logentry_post_save(sender, instance, **kwargs):
    if instance.action_type in [
        'pretix.event.order.secret.changed', 'pretix.event.order.changed.secret', 'pretix.event.order.changed.cancel',
        'pretix.event.order.changed.split'
    ]:
        instance_data = json.loads(instance.data)

        if 'position' and 'positionid' in instance_data:
            # {"position": 4, "positionid": 1} --> changed OrderPosition
            op = OrderPosition.objects.get(order=instance.object_id, id=instance_data['position'])
            tasks.shred_object.apply_async(args=(op.id,))
        else:
            # {} --> whole changed Order
            ops = OrderPosition.objects.filter(order=instance.object_id)
            for op in ops:
                tasks.shred_object.apply_async(args=(op.id,))
    elif instance.action_type in ['pretix.event.order.changed.item', 'pretix.event.order.changed.price', 'pretix.event.order.changed.subevent']:
        instance_data = json.loads(instance.data)
        op = OrderPosition.objects.get(order=instance.object_id, id=instance_data['position'])

        tasks.refresh_object.apply_async(args=(op.id,), countdown=5)
    elif instance.action_type in ['pretix.event.tickets.provider.googlepaypasses', 'pretix.event.changed', 'pretix.event.settings']:
        event = Event.objects.get(id=instance.event_id)

        tasks.refresh_class.apply_async(args=(event.id,), countdown=5)
    elif instance.action_type in ['pretix.organizer.settings']:
        events = Event.objects.filter(organizer_id=instance.object_id, plugins__contains='pretix_googlepaypasses')

        for event in events:
            tasks.refresh_class.apply_async(args=(event.id,), countdown=5)


@receiver(signal=periodic_task)
def shred_unused_objects(sender, **kwargs):
    # Oh well...
    # Google does supposedly report if a WalletObject has any users...
    #
    # hasUsers - boolean - Indicates if the object has users. This field is set by the platform
    #
    # Guess what: it doesn't work and reports "hasUsers -> False" even when the object is installed.
    # Perhaps this is just a timing issue (Result is cached on the Google-side?) - but for now we cannot
    # offer automatic shredding of unused passes. Sucks :-(

    # ops = OrderPosition.objects.filter(meta_info__contains='"googlepaypass"')
    # for op in ops:
    #     comms = Comms(op.event.settings.get('googlepaypasses_credentials'))
    #     meta_info = json.loads(op.meta_info or '{}')
    #     object_id = meta_info['googlepaypass']
    #
    #     item = comms.get_item(ObjectType.eventTicketObject, object_id)
    #
    #     if item and not item['hasUsers']:
    #         tasks.shred_object(op.pk)

    return


settings_hierarkey.add_default(
    'ticketoutput_googlepaypasses_disclaimer_text',
    LazyI18nString.from_gettext(gettext_noop(
        "Please be aware, that contrary to other virtual wallets/passes (like Apple Wallet), Google Pay Passes are not "
        "handled offline. Every pass that is created, has to be transmitted to Google Inc.\r\n"
        "\r\n"
        "By clicking the **Save to phone**-button below, we will transfer some of your personal information, which is "
        "necessary to provide you with your Google Pay Pass, to Google Inc.\r\n"
        "\r\n"
        "Please be aware, that there is no way to delete the data, once it has been transmitted.\r\n"
        "\r\n"
        "However we will anonymize all passes that are not linked to a device on a regular, best effort basis. While "
        "this will remove your personal information from the pass, we cannot guarantee that Google is not keeping a "
        "history of the previous passes.")),
    LazyI18nString
)
