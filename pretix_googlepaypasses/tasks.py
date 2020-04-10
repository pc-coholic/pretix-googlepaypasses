import json
from json import JSONDecodeError

from django_scopes import scopes_disabled
from pretix.base.models import Event, OrderPosition
from pretix.celery_app import app
from pretix_googlepaypasses.googlepaypasses import WalletobjectOutput
from pretix_googlepaypasses.helpers import get_class_id
from walletobjects import EventTicketObject, utils
from walletobjects.comms import Comms
from walletobjects.constants import ClassType, ObjectState, ObjectType


@app.task
@scopes_disabled()
def shred_object(op_id):
    op = OrderPosition.objects.get(id=op_id)

    meta_info = json.loads(op.meta_info or '{}')

    if 'googlepaypass' not in meta_info:
        return True

    object_id = meta_info['googlepaypass']
    class_id = get_class_id(op.order.event)
    output_class = EventTicketObject(object_id, class_id, ObjectState.inactive, op.order.event.settings.locale)
    comms = Comms(op.event.settings.get('googlepaypasses_credentials'))

    if comms.put_item(ClassType.eventTicketClass, class_id, output_class):
        # Remove googlepaypass from OrderPostition meta_info once it has been shredded
        meta_info.pop('googlepaypass')
        op.meta_info = json.dumps(meta_info)
        op.save(update_fields=['meta_info'])
        return True


@app.task
def refresh_object(op_id):
    op = OrderPosition.objects.get(id=op_id)
    meta_info = json.loads(op.meta_info or '{}')

    if 'googlepaypass' not in meta_info:
        return True

    object_id = meta_info['googlepaypass']
    comms = Comms(op.event.settings.get('googlepaypasses_credentials'))

    if comms.get_item(ObjectType.eventTicketObject, object_id):
        return WalletobjectOutput(op.event).generate(op)


@app.task
def refresh_class(event_id):
    event = Event.objects.get(id=event_id)
    comms = Comms(event.settings.get('googlepaypasses_credentials'))
    class_id = get_class_id(event)

    if comms.get_item(ClassType.eventTicketClass, class_id):
        return WalletobjectOutput(event)._generate_class(event)


@app.task
@scopes_disabled()
def process_webhook(webhook_body, issuer_id):
    try:
        webhook_json = json.loads(webhook_body)
    except JSONDecodeError:
        return False

    webhook_json = utils.unseal_callback(webhook_json, issuer_id)

    if 'objectId' and 'eventType' in webhook_json:
        if webhook_json['eventType'] == 'del':
            op = OrderPosition.objects.filter(
                meta_info__contains='"googlepaypass": "{}"'.format(webhook_json['objectId'])
            ).first()

            if op:
                shred_object.apply_async(args=(op.id,))

        elif webhook_json['eventType'] == 'save':
            pass

        return True

    return False
