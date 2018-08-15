import tempfile
from collections import OrderedDict
from typing import Tuple

import pytz
from django import forms
from django.core.files.storage import default_storage
from django.template.loader import get_template
from django.utils.translation import ugettext, ugettext_lazy as _
from pretix.base.models import OrderPosition
from pretix.base.ticketoutput import BaseTicketOutput
from pretix.multidomain.urlreverse import build_absolute_uri

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

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
        tz = pytz.timezone(order.event.settings.timezone)

        return 'googlepaypass-%s-%s.html' % (self.event.slug, order.code), 'text/html', "Hello World"

    def settings_content_render(self, request) -> str:
        if self.event.settings.get('passbook_gmaps_api_key') and self.event.location:
            template = get_template('pretix_googlepaypasses/form.html')
            return template.render({
                'request': request
            })

    def getWalletObjectJWT(order):
        if order:
            authed_session = WalletobjectOutput.getAuthedSession(order.event.settings)
            return "JWT Token should be here"
        else:
            return False

    def getAuthedSession(settings):
        try:
            credentials = service_account.Credentials.from_service_account_info(
                json.loads(settings.get('googlepaypasses_credentials')),
                scopes=['https://www.googleapis.com/auth/wallet_object.issuer'],
            )

            authed_session = AuthorizedSession(credentials)
            return authed_session
        except:
            return False
