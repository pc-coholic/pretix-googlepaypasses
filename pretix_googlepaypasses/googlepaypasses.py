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
from google.auth.transport.requests import AuthorizedSession

from urllib.parse import urljoin

from walletobjects import eventTicketClass
from walletobjects.constants import reviewStatus, multipleDevicesAndHoldersAllowedStatus, confirmationCode, doorsOpen

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

    def getWalletObjectJWT(order):
        if order:
            authedSession = WalletobjectOutput.getAuthedSession(order.event.settings)
            eventticketClass = WalletobjectOutput.getOrGenerateEventticketClass(order, authedSession)
            return "JWT Token should be here; Class: %s" % (eventticketClass)
        else:
            return False

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

    def constructClassName(order):
        gs = GlobalSettingsObject()
        if not gs.settings.get('update_check_id'):
            gs.settings.set('update_check_id', uuid.uuid4().hex)

        issuerId = order.event.settings.get('googlepaypasses_issuer_id')

        return "%s.pretix-%s-%s-%s" % (issuerId, gs.settings.get('update_check_id'), order.event.organizer.slug, order.event.slug)

    def getOrGenerateEventticketClass(order, authedSession):
        eventticketclassName = WalletobjectOutput.constructClassName(order)
        result = authedSession.get(
            'https://www.googleapis.com/walletobjects/v1/eventTicketClass/%s'
                % (eventticketclassName)
        )
        if result.status_code == 404:
            WalletobjectOutput.generateEventticketClass(order, authedSession)
            pass

        return eventticketclassName

    def generateEventticketClass(order, authedSession):
        gs = GlobalSettingsObject()
        eventticketclassName = WalletobjectOutput.constructClassName(order)

        evTclass = eventTicketClass(
            order.event.organizer.name,
            eventticketclassName,
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
                urljoin(settings.SITE_URL, order.event.settings.get('ticketoutput_googlepaypasses_hero').url),
                str(order.event.name),
                order.event.name,
            )

        evTclass.hexBackgroundColor(order.event.settings.get('primary_color'))
        evTclass.eventId('pretix-%s-%s-%s' % (gs.settings.get('update_check_id'), order.event.organizer.slug, order.event.slug))

        if order.event.settings.get('ticketoutput_googlepaypasses_logo'):
            evTclass.logo(
                urljoin(settings.SITE_URL, order.event.settings.get('ticketoutput_googlepaypasses_logo').url),
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
                str(order.event.date_admission),
                str(order.event.date_from),
                str(order.event.date_to),
            )

        #evTclass.finePrint()

        evTclass.confirmationCodeLabel(confirmationCode.orderNumber)

        #evTclass.seatLabel()
        #evTclass.rowLabel()
        #evTclass.sectionLabel()
        #evTclass.gateLabel()

        print(evTclass)

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
