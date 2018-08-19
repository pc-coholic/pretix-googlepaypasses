import tempfile
from collections import OrderedDict
from typing import Tuple
import uuid
import json

import pytz
from django import forms
from django.core.files.storage import default_storage
from django.template.loader import get_template
from django.utils import translation
from django.utils.translation import ugettext, ugettext_lazy as _
from pretix.base.models import OrderPosition
from pretix.base.ticketoutput import BaseTicketOutput
from pretix.multidomain.urlreverse import build_absolute_uri, eventreverse
from pretix.base.settings import GlobalSettingsObject
from django.conf import settings

from google.oauth2 import service_account
from google.auth import crypt, jwt
from google.auth.transport.requests import AuthorizedSession

from urllib.parse import urljoin

from walletobjects import eventTicketClass, eventTicketObject, buttonJWT
from walletobjects.constants import reviewStatus, multipleDevicesAndHoldersAllowedStatus, confirmationCode, doorsOpen, objectState, barcode

from .forms import PNGImageField

class WalletobjectOutput(BaseTicketOutput):
    identifier = 'googlepaypasses'
    verbose_name = 'Google Pay Passes'
    download_button_icon = 'fa-google'
    download_button_text = _('Pay | Save to phone')
    multi_download_enabled = False

    @property
    def settings_form_fields(self) -> dict:
        return OrderedDict(
            list(super().settings_form_fields.items()) + [
                ('dataprotection_approval',
                 forms.BooleanField(
                    label=_('I agree to transmit my participants\' personal data to Google Inc.'),
                    help_text=_('Please be aware, that contrary to other virtual wallets/passes (like Apple Wallet), '
                                'Google Pay Passes are not handled offline. Every pass that is created will be '
                                'transmitted to Google Inc.'
                                '<br><br>'
                                'Your participants will be prompted to agree before each transmission, but you might '
                                'want to add a section concerning this issue to your privacy policy.'
                                '<br><br>'
                                'If you require more information or guidance on this subject, please contact your '
                                'legal counsel.'),
                    required=True,
                 )),
                ('logo',
                 PNGImageField(
                     label=_('Event logo'),
                     help_text=_('<a href="https://developers.google.com/pay/passes/guides/pass-verticals/event-tickets/design">#1</a> '
                                 '- Minimum size is 660 x 660 pixels. We suggest an upload size of 1200 x 1200 pixels.'
                                 '<br><br>'
                                 'Please see <a href="https://developers.google.com/pay/passes/guides/get-started/api-guidelines/brand-guidelines#logo-image-guidelines">'
                                 'Google Pay API for Passes Brand guidelines</a> for more detailed information.'),
                     required=False,
                 )),
                ('hero',
                 PNGImageField(
                     label=_('Hero image'),
                     help_text=_('<a href="https://developers.google.com/pay/passes/guides/pass-verticals/event-tickets/design">#6</a> '
                                 '- Minimum aspect ratio is 3:1, or wider. We suggest an upload size of 1032 x 336 pixels.'
                                 '<br><br>'
                                 'Please see <a href="https://developers.google.com/pay/passes/guides/get-started/api-guidelines/brand-guidelines#hero-image-guidelines">'
                                 'Google Pay API for Passes Brand guidelines</a> for more detailed information.'),
                     required=False,
                 )),
                ('latitude',
                 forms.FloatField(
                     label=_('Event location (latitude)'),
                     required=False
                 )),
                ('longitude',
                 forms.FloatField(
                     label=_('Event location (longitude)'),
                     required=False
                 )),
            ]
        )

    def generate(self, order_position: OrderPosition) -> Tuple[str, str, str]:
        order = order_position.order
        ev = order_position.subevent or order.event
        tz = pytz.timezone(order.event.settings.get('timezone'))

        return 'googlepaypass-%s-%s.html' % (self.event.slug, order.code), 'text/html', "Hello World"

    def settings_content_render(self, request) -> str:
        if self.event.settings.get('passbook_gmaps_api_key') and self.event.location:
            template = get_template('pretix_googlepaypasses/form.html')
            return template.render({
                'request': request
            })

    def getWalletObjectJWT(order, positionid):
        if not order:
            return False

        authedSession = WalletobjectOutput.getAuthedSession(order.event.settings)

        if not authedSession:
            return False

        eventTicketClass = WalletobjectOutput.getOrgenerateEventTicketClass(order, authedSession)

        if not eventTicketClass:
            return False

        op = OrderPosition.objects.get(order=order, positionid=positionid)
        if not op:
            return False

        eventTicketObject = WalletobjectOutput.getOrGenerateEventTicketObject(op, authedSession)

        if not str(eventTicketObject):
            return False

        walletobjectJWT = WalletobjectOutput.generateWalletobjectJWT(order.event.settings, eventTicketObject)

        if not walletobjectJWT:
            return False

        #return 'JWT Token should be here; Class: %s; Object: %s; JWT: %s' % (eventTicketClass, eventTicketObject['id'], walletobjectJWT)
        return walletobjectJWT

    def getAuthedSession(settings):
        try:
            credentials = service_account.Credentials.from_service_account_info(
                json.loads(settings.get('googlepaypasses_credentials')),
                scopes=['https://www.googleapis.com/auth/wallet_object.issuer'],
            )

            authedSession = AuthorizedSession(credentials)
            return authedSession
        except:
            return False

    def constructClassID(order):
        gs = GlobalSettingsObject()
        if not gs.settings.get('update_check_id'):
            gs.settings.set('update_check_id', uuid.uuid4().hex)

        issuerId = order.event.settings.get('googlepaypasses_issuer_id')

        return "%s.pretix-%s-%s-%s" % (issuerId, gs.settings.get('update_check_id'),
                                       order.event.organizer.slug, order.event.slug)

    def constructObjectID(op):
        gs = GlobalSettingsObject()
        if not gs.settings.get('update_check_id'):
            gs.settings.set('update_check_id', uuid.uuid4().hex)

        issuerId = op.order.event.settings.get('googlepaypasses_issuer_id')

        return "%s.pretix-%s-%s-%s-%s-%s" % (issuerId, gs.settings.get('update_check_id'),
                                             op.order.event.organizer.slug, op.order.event.slug,
                                             op.order.code, op.positionid)

    def getOrgenerateEventTicketClass(order, authedSession):
        eventTicketClassName = WalletobjectOutput.constructClassID(order)
        result = authedSession.get(
            'https://www.googleapis.com/walletobjects/v1/eventTicketClass/%s'
                % (eventTicketClassName)
        )

        if result.status_code == 404:
            return WalletobjectOutput.generateEventTicketClass(order, authedSession)
        elif result.status_code == 200:
            return eventTicketClassName
        else:
            return False

    def getOrGenerateEventTicketObject(op, authedSession):
        meta_info = json.loads(op.meta_info)

        if 'googlepaypass' in meta_info:
            #eventTicketObject = WalletobjectOutput.generateEventTicketObject(op, authedSession, ship=False)
            eventTicketObject = WalletobjectOutput.generateEventTicketObject(op, authedSession, ship=True, update=True)
        else:
            eventTicketObject = WalletobjectOutput.generateEventTicketObject(op, authedSession)

        if str(eventTicketObject) and 'googlepaypass' not in meta_info:
            meta_info['googlepaypass'] = eventTicketObject['id']
            op.meta_info = json.dumps(meta_info)
            op.save(update_fields=['meta_info'])
            return eventTicketObject
        elif str(eventTicketObject) and 'googlepaypass' in meta_info:
            return eventTicketObject
        else:
            return False

    def generateEventTicketClass(order, authedSession, update=False):
        gs = GlobalSettingsObject()
        eventTicketClassName = WalletobjectOutput.constructClassID(order)

        evTclass = eventTicketClass(
            order.event.organizer.name,
            eventTicketClassName,
            multipleDevicesAndHoldersAllowedStatus.multipleHolders, # TODO: Make configurable
            order.event.name,
            reviewStatus.underReview,
            order.event.settings.locale
        )

        #evTclass.localizedIssuerName()
        #evTclass.messages()

        evTclass.homepageUri(
            build_absolute_uri(order.event, 'presale:event.index'),
            WalletobjectOutput.getTranslatedString('Website', order.event.settings.get('locale')),
            WalletobjectOutput.getTranslatedDict('Website', order.event.settings.get('locales'))
        )

        #evTclass.imageModulesData()
        #evTclass.linksModuleData()

        if (order.event.settings.get('ticketoutput_googlepaypasses_latitude')
            and order.event.settings.get('ticketoutput_googlepaypasses_longitude')):
                evTclass.locations(
                    order.event.settings.get('ticketoutput_googlepaypasses_latitude'),
                    order.event.settings.get('ticketoutput_googlepaypasses_longitude')
                )

        #evTclass.textModulesData()

        evTclass.countryCode(order.event.settings.get('locale'))

        evTclass.hideBarcode(False)

        if order.event.settings.get('ticketoutput_googlepaypasses_hero'):
            evTclass.heroImage(
                #urljoin(settings.SITE_URL, order.event.settings.get('ticketoutput_googlepaypasses_hero').url),
                'https://us.pc-coholic.de/pretix-hero.jpg',
                str(order.event.name),
                order.event.name,
            )

        evTclass.hexBackgroundColor(order.event.settings.get('primary_color'))
        evTclass.eventId('pretix-%s-%s-%s' % (gs.settings.get('update_check_id'), order.event.organizer.slug, order.event.slug))

        if order.event.settings.get('ticketoutput_googlepaypasses_logo'):
            evTclass.logo(
                #urljoin(settings.SITE_URL, order.event.settings.get('ticketoutput_googlepaypasses_logo').url),
                'https://us.pc-coholic.de/pretix-logo.png',
                str(order.event.name),
                order.event.name,
            )

        if order.event.location:
            name = {}
            address = {}

            for key, value in order.event.location.data.items():
                name[key] = value.splitlines()[0]
                address[key] = value.splitlines()[1]

            evTclass.venue(name, address)

        if order.event.date_from and order.event.date_to and order.event.date_admission:
            evTclass.dateTime(
                doorsOpen.doorsOpen,
                order.event.date_admission.isoformat(),
                order.event.date_from.isoformat(),
                order.event.date_to.isoformat(),
            )

        #evTclass.finePrint()

        evTclass.confirmationCodeLabel(confirmationCode.orderNumber)

        #evTclass.seatLabel()
        #evTclass.rowLabel()
        #evTclass.sectionLabel()
        #evTclass.gateLabel()

        if update:
            result = authedSession.put(
                'https://www.googleapis.com/walletobjects/v1/eventTicketClass/%s?strict=true' % WalletobjectOutput.constructClassID(order),
                json = json.loads(str(evTclass))
            )
        else:
            result = authedSession.post(
                'https://www.googleapis.com/walletobjects/v1/eventTicketClass?strict=true',
                json = json.loads(str(evTclass))
            )

        if result.status_code == 200:
            return eventTicketClassName
        else:
            # TODO: Perhaps log the error?
            print(result.status_code)
            print(result.text)
            return False

    def generateEventTicketObject(op, authedSession, update=False, ship=True):
        eventTicketClassName = WalletobjectOutput.constructClassID(op.order)
        meta_info = json.loads(op.meta_info)

        if update:
            evTobjectID = meta_info['googlepaypass']
        else:
            evTobjectID = WalletobjectOutput.constructObjectID(op)

        evTobject = eventTicketObject(evTobjectID, eventTicketClassName, objectState.active, op.order.event.settings.locale)

        evTobject.barcode(barcode.qrCode, op.secret)

        #evTobject.messages()
        #evTobject.validTimeInterval()
        #evTobject.locations()
        #evTobject.disableExpirationNotification()
        #evTobject.infoModuleData()
        #evTobject.imageModulesData()
        #evTobject.textModulesData()
        #evTobject.linksModuleData()
        #evTobject.seat()
        #evTobject.row()
        #evTobject.section()
        #evTobject.gate()

        evTobject.reservationInfo("%s-%s" % (op.order.event.slug, op.order.code))
        evTobject.ticketHolderName(op.attendee_name or (op.addon_to.attendee_name if op.addon_to else ''))
        evTobject.ticketNumber(op.secret)
        evTobject.ticketType(WalletobjectOutput.getTranslatedDict(str(op.item) + (" – " + str(op.variation.value) if op.variation else ""), op.order.event.settings.get('locales')))

        places = settings.CURRENCY_PLACES.get(op.order.event.currency, 2)
        evTobject.faceValue(int(op.price * 1000 ** places), op.order.event.currency)

        if ship:
            if update:
                result = authedSession.put(
                    'https://www.googleapis.com/walletobjects/v1/eventTicketObject/%s?strict=true' % evTobjectID,
                    json = json.loads(str(evTobject))
                )
            else:
                result = authedSession.post(
                    'https://www.googleapis.com/walletobjects/v1/eventTicketObject?strict=true',
                    json = json.loads(str(evTobject))
                )

            if result.status_code == 200:
                return evTobject
            else:
                # TODO: Perhaps log the error?
                print(result.status_code)
                print(result.text)
                return False
        else:
            return evTobject

    def generateWalletobjectJWT(settings, payload):
        button = buttonJWT(
            origins=['http://localhost/'],
            issuer='pretix-googlepaypasses@pretix-gpaypasses.iam.gserviceaccount.com',
            eventTicketObjects = [json.loads(str(payload))],
        )
        signer = crypt.RSASigner.from_service_account_info(json.loads(settings.get('googlepaypasses_credentials')))
        payload = json.loads(str(button))
        encoded = jwt.encode(signer, payload)
        if not encoded:
            return False

        return encoded.decode("utf-8")

    def getTranslatedDict(string, locales):
        translatedDict = {}

        for locale in locales:
            translation.activate(locale)
            translatedDict[locale] = ugettext(string)
            translation.deactivate()

        return translatedDict

    def getTranslatedString(string, locale):
        translation.activate(locale)
        translatedString = ugettext(string)
        translation.deactivate()
        return translatedString
