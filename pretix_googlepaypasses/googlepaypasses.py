import json
import uuid
from collections import OrderedDict
from typing import Tuple
from urllib.parse import urljoin

from django import forms
from django.conf import settings
from django.template.loader import get_template
from django.utils import translation
from django.utils.translation import ugettext, ugettext_lazy as _
from google.auth import crypt, jwt
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from pretix.base.models import OrderPosition
from pretix.base.settings import GlobalSettingsObject
from pretix.base.ticketoutput import BaseTicketOutput
from pretix.multidomain.urlreverse import build_absolute_uri
from walletobjects import buttonJWT, eventTicketClass, eventTicketObject
from walletobjects.constants import (
    barcode, confirmationCode, doorsOpen,
    multipleDevicesAndHoldersAllowedStatus, objectState, reviewStatus,
)

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
        # ev = order_position.subevent or order.event
        # tz = pytz.timezone(order.event.settings.get('timezone'))

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

        eventTicketClass = WalletobjectOutput.getOrgenerateEventTicketClass(order.event, authedSession)

        if not eventTicketClass:
            return False

        op = OrderPosition.objects.get(order=order, id=positionid)

        if not op:
            return False

        eventTicketObject = WalletobjectOutput.getOrGenerateEventTicketObject(op, authedSession)

        if not eventTicketObject:
            return False

        walletobjectJWT = WalletobjectOutput.generateWalletobjectJWT(order.event.settings, eventTicketObject)

        if not walletobjectJWT:
            return False

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

    def constructClassID(event):
        gs = GlobalSettingsObject()
        if not gs.settings.get('update_check_id'):
            gs.settings.set('update_check_id', uuid.uuid4().hex)

        issuerId = event.settings.get('googlepaypasses_issuer_id')

        return "%s.pretix-%s-%s-%s" % (issuerId, gs.settings.get('update_check_id'),
                                       event.organizer.slug, event.slug)

    def constructObjectID(op):
        gs = GlobalSettingsObject()
        if not gs.settings.get('update_check_id'):
            gs.settings.set('update_check_id', uuid.uuid4().hex)

        issuerId = op.order.event.settings.get('googlepaypasses_issuer_id')

        return "%s.pretix-%s-%s-%s-%s-%s-%s" % (issuerId, gs.settings.get('update_check_id'),
                                                op.order.event.organizer.slug, op.order.event.slug,
                                                op.order.code, op.positionid, uuid.uuid4().hex)

    def getOrgenerateEventTicketClass(event, authedSession):
        eventTicketClassName = WalletobjectOutput.constructClassID(event)
        result = authedSession.get(
            'https://www.googleapis.com/walletobjects/v1/eventTicketClass/%s' % (eventTicketClassName)
        )

        if result.status_code == 404:
            return WalletobjectOutput.generateEventTicketClass(event, authedSession)
        elif result.status_code == 200:
            return eventTicketClassName
        else:
            return False

    def checkIfEventTicketClassExists(event, authedSession):
        eventTicketClassName = WalletobjectOutput.constructClassID(event)
        result = authedSession.get(
            'https://www.googleapis.com/walletobjects/v1/eventTicketClass/%s' % (eventTicketClassName)
        )

        if result.status_code == 200:
            return eventTicketClassName
        else:
            return False

    def getOrGenerateEventTicketObject(op, authedSession):
        meta_info = json.loads(op.meta_info or '{}')

        if 'googlepaypass' in meta_info:
            eventTicketObject = WalletobjectOutput.generateEventTicketObject(op, authedSession, ship=False)
        else:
            eventTicketObject = WalletobjectOutput.generateEventTicketObject(op, authedSession)

        if eventTicketObject and 'googlepaypass' not in meta_info:
            meta_info['googlepaypass'] = eventTicketObject['id']
            op.meta_info = json.dumps(meta_info)
            op.save(update_fields=['meta_info'])
            return eventTicketObject
        elif eventTicketObject and 'googlepaypass' in meta_info:
            return eventTicketObject
        else:
            return False

    def generateEventTicketClass(event, authedSession, update=False):
        gs = GlobalSettingsObject()
        eventTicketClassName = WalletobjectOutput.constructClassID(event)

        evTclass = eventTicketClass(
            event.organizer.name,
            eventTicketClassName,
            multipleDevicesAndHoldersAllowedStatus.multipleHolders,  # TODO: Make configurable
            event.name,
            reviewStatus.underReview,
            event.settings.locale
        )

        evTclass.homepageUri(
            build_absolute_uri(event, 'presale:event.index'),
            WalletobjectOutput.getTranslatedString('Website', event.settings.get('locale')),
            WalletobjectOutput.getTranslatedDict('Website', event.settings.get('locales'))
        )

        if (event.settings.get('ticketoutput_googlepaypasses_latitude')
           and event.settings.get('ticketoutput_googlepaypasses_longitude')):
                evTclass.locations(
                    event.settings.get('ticketoutput_googlepaypasses_latitude'),
                    event.settings.get('ticketoutput_googlepaypasses_longitude')
                )

        evTclass.countryCode(event.settings.get('locale'))

        evTclass.hideBarcode(False)

        if event.settings.get('ticketoutput_googlepaypasses_hero'):
            evTclass.heroImage(
                # urljoin(settings.SITE_URL, order.event.settings.get('ticketoutput_googlepaypasses_hero').url),
                'https://us.pc-coholic.de/pretix-hero.jpg',
                str(event.name),
                event.name,
            )

        evTclass.hexBackgroundColor(event.settings.get('primary_color'))
        evTclass.eventId('pretix-%s-%s-%s' % (gs.settings.get('update_check_id'), event.organizer.slug, event.slug))

        if event.settings.get('ticketoutput_googlepaypasses_logo'):
            evTclass.logo(
                # urljoin(settings.SITE_URL, event.settings.get('ticketoutput_googlepaypasses_logo').url),
                'https://us.pc-coholic.de/pretix-logo.png',
                str(event.name),
                event.name,
            )

        if event.location:
            name = {}
            address = {}

            for key, value in event.location.data.items():
                name[key] = value.splitlines()[0]
                address[key] = value.splitlines()[1]

            evTclass.venue(name, address)

        if event.date_from and event.date_to and event.date_admission:
            evTclass.dateTime(
                doorsOpen.doorsOpen,
                event.date_admission.isoformat(),
                event.date_from.isoformat(),
                event.date_to.isoformat(),
            )

        evTclass.confirmationCodeLabel(confirmationCode.orderNumber)

        if update:
            result = authedSession.put(
                'https://www.googleapis.com/walletobjects/v1/eventTicketClass/%s?strict=true' % WalletobjectOutput.constructClassID(event),
                json=json.loads(str(evTclass))
            )
        else:
            result = authedSession.post(
                'https://www.googleapis.com/walletobjects/v1/eventTicketClass?strict=true',
                json=json.loads(str(evTclass))
            )

        if result.status_code == 200:
            return eventTicketClassName
        else:
            # TODO: Perhaps log the error?
            print(result.status_code)
            print(result.text)
            return False

    def generateEventTicketObject(op, authedSession, update=False, ship=True):
        eventTicketClassName = WalletobjectOutput.constructClassID(op.order.event)
        meta_info = json.loads(op.meta_info or '{}')

        if update:
            evTobjectID = meta_info['googlepaypass']
        else:
            evTobjectID = WalletobjectOutput.constructObjectID(op)

        evTobject = eventTicketObject(evTobjectID, eventTicketClassName, objectState.active, op.order.event.settings.locale)

        evTobject.barcode(barcode.qrCode, op.secret)

        evTobject.reservationInfo("%s-%s" % (op.order.event.slug, op.order.code))
        evTobject.ticketHolderName(op.attendee_name or (op.addon_to.attendee_name if op.addon_to else ''))
        evTobject.ticketNumber(op.secret)
        evTobject.ticketType(
            WalletobjectOutput.getTranslatedDict(
                str(op.item) + (" – " + str(op.variation.value) if op.variation else ""),
                op.order.event.settings.get('locales')
            )
        )

        places = settings.CURRENCY_PLACES.get(op.order.event.currency, 2)
        evTobject.faceValue(int(op.price * 1000 ** places), op.order.event.currency)

        if ship:
            if update:
                result = authedSession.put(
                    'https://www.googleapis.com/walletobjects/v1/eventTicketObject/%s?strict=true' % evTobjectID,
                    json=json.loads(str(evTobject))
                )
            else:
                result = authedSession.post(
                    'https://www.googleapis.com/walletobjects/v1/eventTicketObject?strict=true',
                    json=json.loads(str(evTobject))
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
        credentials = json.loads(settings.get('googlepaypasses_credentials'))

        button = buttonJWT(
            origins=[settings.SITE_URL],
            issuer=credentials['client_email'],
            eventTicketObjects=[json.loads(str(payload))],
        )
        signer = crypt.RSASigner.from_service_account_info(credentials)
        payload = json.loads(str(button))
        encoded = jwt.encode(signer, payload)

        if not encoded:
            return False

        return encoded.decode("utf-8")

    def shredEventTicketObject(op, authedSession):
        meta_info = json.loads(op.meta_info or '{}')

        if 'googlepaypass' not in meta_info:
            return True

        evTobjectID = meta_info['googlepaypass']
        eventTicketClassName = WalletobjectOutput.constructClassID(op.order.event)
        evTobject = eventTicketObject(evTobjectID, eventTicketClassName, objectState.inactive, op.order.event.settings.locale)

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
