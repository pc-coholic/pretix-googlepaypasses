import json
from json import JSONDecodeError

from django_scopes import scopes_disabled

from .helpers import get_class_id
from pretix.base.models import Event, Order, OrderPosition
from pretix.celery_app import app
from walletobjects import eventTicketObject, utils
from walletobjects.constants import ObjectState

from .googlepaypasses import WalletobjectOutput


@app.task
@scopes_disabled()
def shredEventTicketObject(opId):
    op = OrderPosition.objects.get(id=opId)
    authedSession = WalletobjectOutput.getAuthedSession(op.event.settings)

    meta_info = json.loads(op.meta_info or '{}')

    if 'googlepaypass' not in meta_info:
        return True

    evTobjectID = meta_info['googlepaypass']
    eventTicketClassName = get_class_id(op.order.event)
    evTobject = eventTicketObject(evTobjectID, eventTicketClassName, objectState.inactive,
                                  op.order.event.settings.locale)

    result = authedSession.put(
        'https://www.googleapis.com/walletobjects/v1/eventTicketObject/%s?strict=true' % evTobjectID,
        json=json.loads(str(evTobject))
    )

    if result.status_code == 200:
        # Remove googlepaypass from OrderPostition meta_info once it has been shredded
        meta_info.pop('googlepaypass')
        op.meta_info = json.dumps(meta_info)
        op.save(update_fields=['meta_info'])
        return True
    else:
        print(result.status_code)
        print(result.text)
        return False


@app.task
def generateEventTicketClassIfExisting(eventId):
    event = Event.objects.get(id=eventId)
    authedSession = WalletobjectOutput.getAuthedSession(event.settings)

    if WalletobjectOutput.checkIfEventTicketClassExists(event, authedSession):
        generateEventTicketClass.apply_async(args=(event.id, True))


@app.task
def generateEventTicketClass(eventId, update=False):
    event = Event.objects.get(id=eventId)
    authedSession = WalletobjectOutput.getAuthedSession(event.settings)

    WalletobjectOutput.generateEventTicketClass(event, authedSession, update)


@app.task
def generateEventTicketObjectIfExisting(opId):
    op = OrderPosition.objects.get(id=opId)
    authedSession = WalletobjectOutput.getAuthedSession(op.event.settings)

    walletObject = WalletobjectOutput.getOrGenerateEventTicketObject(op, authedSession)

    if (walletObject):
        generateEventTicketObject.apply_async(args=(opId, True, True))


@app.task
def generateEventTicketObject(opId, update=False, ship=False):
    op = OrderPosition.objects.get(id=opId)
    authedSession = WalletobjectOutput.getAuthedSession(op.event.settings)

    WalletobjectOutput.generateEventTicketObject(op, authedSession, update, ship)


@app.task
@scopes_disabled()
def procesWebhook(webhookbody, issuerId):
    try:
        webhook_json = json.loads(webhookbody)
    except JSONDecodeError:
        return False

    webhook_json = utils.unsealCallback(webhook_json, issuerId)

    if 'objectId' and 'eventType' in webhook_json:
        if webhook_json['eventType'] == 'del':
            op = OrderPosition.objects.filter(
                meta_info__contains='"googlepaypass": "{}"'.format(webhook_json['objectId'])
            ).first()

            if op:
                shredEventTicketObject.apply_async(args=(op.id,))

        elif webhook_json['eventType'] == 'save':
            pass

        return True

    return False
