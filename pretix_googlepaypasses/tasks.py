import json
from pretix.base.models import Order, OrderPosition, Event
from .googlepaypasses import WalletobjectOutput
from pretix.celery_app import app
from walletobjects import eventTicketObject
from walletobjects.constants import objectState

@app.task
def generateWalletObjectJWT(orderId, positionId):
    order = Order.objects.get(id=orderId)

    return WalletobjectOutput.getWalletObjectJWT(order, positionId)

@app.task
def shredEventTicketObject(opId):
    op = OrderPosition.objects.get(id=opId)
    authedSession = WalletobjectOutput.getAuthedSession(op.event.settings)

    meta_info = json.loads(op.meta_info or '{}')

    if 'googlepaypass' not in meta_info:
        return True

    evTobjectID = meta_info['googlepaypass']
    eventTicketClassName = WalletobjectOutput.constructClassID(op.order.event)
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