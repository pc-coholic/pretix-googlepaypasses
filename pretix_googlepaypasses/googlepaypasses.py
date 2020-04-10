import json
from collections import OrderedDict
from typing import Tuple
from urllib.parse import urljoin

from django import forms
from django.conf import settings as django_settings
from django.templatetags.static import static
from django.utils.translation import ugettext_lazy as _  # NoQA
from i18nfield.forms import I18nFormField, I18nTextarea
from pretix.base.models import Event, OrderPosition
from pretix.base.settings import GlobalSettingsObject
from pretix.base.ticketoutput import BaseTicketOutput
from pretix.multidomain.urlreverse import build_absolute_uri
from pretix_googlepaypasses.forms import PNGImageField
from pretix_googlepaypasses.helpers import (
    get_class_id, get_object_id, get_translated_dict, get_translated_string,
)
from walletobjects import ButtonJWT, EventTicketClass, EventTicketObject
from walletobjects.comms import Comms
from walletobjects.constants import (
    Barcode, ClassType, ConfirmationCode, DoorsOpen,
    MultipleDevicesAndHoldersAllowedStatus, ObjectState, ObjectType,
    ReviewStatus, Seat,
)


class WalletobjectOutput(BaseTicketOutput):
    identifier = 'googlepaypasses'
    verbose_name = 'Google Pay Passes'
    download_button_icon = 'fa-google'
    download_button_text = _('Pay | Save to phone')
    multi_download_enabled = False
    preview_allowed = False
    javascript_required = True

    @property
    def settings_form_fields(self) -> dict:
        return OrderedDict(
            list(super().settings_form_fields.items()) + [
                ('dataprotection_approval',
                 forms.BooleanField(
                     label=_("I agree to transmit my participants' personal data to Google Inc."),
                     help_text=_("Please be aware, that contrary to other virtual wallets/passes (like Apple Wallet), "
                                 "Google Pay Passes are not handled offline. Every pass that is created will be "
                                 "transmitted to Google Inc., so you might want to add a section concerning this to "
                                 "your privacy policy."
                                 "<br><br>"
                                 "If you require more information or guidance on this subject, please contact your "
                                 "legal counsel."),
                     required=True,
                 )),
                ('show_disclaimer',
                 forms.BooleanField(
                     label=_("Display a privacy notice to the customers before transmitting data"),
                     help_text=_("By default, your customers will have their Google Pay Passes generated the moment "
                                 "they click the corresponding button. If you want to inform them of the transmission "
                                 "of their personal information to Google beforehand, please enable this option."),
                 )),
                ('disclaimer_text',
                 I18nFormField(
                     label=_("Privacy notice"),
                     required=False,
                     widget=I18nTextarea,
                     widget_kwargs={
                         'attrs': {
                             'data-display-dependency': '#id_ticketoutput_googlepaypasses_show_disclaimer'
                         }
                     },
                     help_text=_("This text will be displayed as a privacy notice if enabled above.")
                 )),
                ('logo',
                 PNGImageField(
                     label=_("Event logo"),
                     help_text='<div class="col-md-3">'
                               '    <img src={}>'
                               '</div>'
                               '<div class="col-md-9">'
                               '    {}'
                               '    <br><br>'
                               '    {}'
                               '    <br><br>'
                               '    {}'
                               '    <br><br>'
                               '    {}'
                               '</div>'.format(
                         static('pretix_googlepaypasses/img/DefaultTemplate_EventTicketPasses.svg'),
                         _("Element #1"),
                         _("Minimum size is 660 x 660 pixels. We suggest an upload size of 1200 x 1200 pixels."),
                         _("Google will verify that the image you are specifying here is reachable from the internet. "
                           "If it is not, the passes cannot be generated and the API will return an error."),
                         _('Please see <a href="{}">Google Pay API for Passes Brand guidelines</a> for more detailed '
                           'information.'.format(
                               'https://developers.google.com/pay/passes/guides/get-started/api-guidelines/'
                               'brand-guidelines#logo-image-guidelines')
                           )
                     ),
                     required=False,
                 )),
                ('hero',
                 PNGImageField(
                     label=_('Hero image'),
                     help_text='<div class="col-md-3">'
                               '    <img src={}>'
                               '</div>'
                               '<div class="col-md-9">'
                               '    {}'
                               '    <br><br>'
                               '    {}'
                               '    <br><br>'
                               '    {}'
                               '    <br><br>'
                               '    {}'
                               '</div>'.format(
                         static('pretix_googlepaypasses/img/DefaultTemplate_EventTicketPasses.svg'),
                         _("Element #8"),
                         _("Minimum aspect ratio is 3:1, or wider. We suggest an upload size of 1032 x 336 pixels."),
                         _("Google will verify that the image you are specifying here is reachable from the internet. "
                           "If it is not, the passes cannot be generated and the API will return an error."),
                         _('Please see <a href="{}">Google Pay API for Passes Brand guidelines</a> for more detailed '
                           'information.'.format(
                               'https://developers.google.com/pay/passes/guides/get-started/api-guidelines/'
                               'brand-guidelines#hero-image-guidelines')
                           )
                     ),
                     required=False,
                 )),
                ('latitude',
                 forms.FloatField(
                     label=_('Event location (latitude)'),
                     help_text=_('Will be taken from event settings by default.'),
                     required=False
                 )),
                ('longitude',
                 forms.FloatField(
                     label=_('Event location (longitude)'),
                     help_text=_('Will be taken from event settings by default.'),
                     required=False
                 )),
            ]
        )

    def generate(self, order_position: OrderPosition) -> Tuple[str, str, str]:
        if not self._get_class(order_position.order.event):
            return False

        ticket_object = self._get_object(order_position)

        if not ticket_object:
            return False

        generated_jwt = self._comms().sign_jwt(
            ButtonJWT(
                origins=[django_settings.SITE_URL],
                issuer=self._comms().client_email,
                event_ticket_objects=[ticket_object],
                skinny=True
            )
        )

        if generated_jwt:
            return 'googlepaypass', 'text/uri-list', 'https://pay.google.com/gp/v/save/%s' % generated_jwt
        else:
            return False

    def _comms(self):
        if not hasattr(self, '__comms'):
            self.__comms = Comms(self.event.settings.get('googlepaypasses_credentials'))

        return self.__comms

    def _get_class(self, event: Event):
        ticket_class = get_class_id(event)

        item = self._comms().get_item(ClassType.eventTicketClass, ticket_class)

        if item is None:
            return False
        elif not item:
            return self._generate_class(event)
        else:
            return ticket_class

    def _generate_class(self, event: Event):
        gs = GlobalSettingsObject()
        class_name = get_class_id(event)

        output_class = EventTicketClass(
            event.organizer.name,
            class_name,
            MultipleDevicesAndHoldersAllowedStatus.multipleHolders,  # TODO: Make configurable
            event.name,
            ReviewStatus.underReview,
            event.settings.locale
        )

        output_class.homepage_uri(
            build_absolute_uri(event, 'presale:event.index'),
            get_translated_string('Website', event.settings.get('locale')),
            get_translated_dict('Website', event.settings.get('locales'))
        )

        output_class.callback_url(build_absolute_uri(event.organizer, 'plugins:pretix_googlepaypasses:webhook'))

        if (event.settings.get('ticketoutput_googlepaypasses_latitude')
                and event.settings.get('ticketoutput_googlepaypasses_longitude')):
            output_class.locations(
                event.settings.get('ticketoutput_googlepaypasses_latitude'),
                event.settings.get('ticketoutput_googlepaypasses_longitude')
            )
        elif event.geo_lat and event.geo_lon:
            output_class.locations(
                event.geo_lat,
                event.geo_lon
            )

        output_class.country_code(event.settings.get('locale'))

        output_class.hide_barcode(False)

        if event.settings.get('ticketoutput_googlepaypasses_hero'):
            output_class.hero_image(
                urljoin(django_settings.SITE_URL, event.settings.get('ticketoutput_googlepaypasses_hero').url),
                str(event.name),
                event.name,
            )

        output_class.hex_background_color(event.settings.get('primary_color'))
        output_class.event_id('pretix-%s-%s-%s' % (gs.settings.get('update_check_id'), event.organizer.id, event.id))

        if event.settings.get('ticketoutput_googlepaypasses_logo'):
            output_class.logo(
                urljoin(django_settings.SITE_URL, event.settings.get('ticketoutput_googlepaypasses_logo').url),
                str(event.name),
                event.name,
            )

        if event.location:
            name = {}
            address = {}

            for key, value in event.location.data.items():
                lines = value.splitlines()
                name[key] = lines[0]
                # We must provide at least one address line each for the name and address - no way around it.
                if len(lines) > 1:
                    address[key] = '\n'.join(value.splitlines()[1:])
                else:
                    address[key] = lines[0]

            output_class.venue(name, address)

        if event.date_from and event.date_to and event.date_admission:
            output_class.date_time(
                DoorsOpen.doorsOpen,
                event.date_admission.isoformat(),
                event.date_from.isoformat(),
                event.date_to.isoformat(),
            )

        output_class.confirmation_code_label(ConfirmationCode.orderNumber)

        if event.seating_plan_id is not None:
            output_class.seat_label(Seat.seat)

        return self._comms().put_item(ClassType.eventTicketClass, class_name, output_class)

    def _get_object(self, op: OrderPosition):
        meta_info = json.loads(op.meta_info or '{}')

        ticket_object = self._generate_object(op)

        if ticket_object and 'googlepaypass' not in meta_info:
            meta_info['googlepaypass'] = ticket_object['id']
            op.meta_info = json.dumps(meta_info)
            op.save(update_fields=['meta_info'])
            return ticket_object
        elif ticket_object and 'googlepaypass' in meta_info:
            return ticket_object
        else:
            return False

    def _generate_object(self, op: OrderPosition):
        class_name = get_class_id(op.order.event)
        meta_info = json.loads(op.meta_info or '{}')

        if 'googlepaypass' in meta_info:
            object_name = meta_info['googlepaypass']
        else:
            object_name = get_object_id(op)

        output_object = EventTicketObject(object_name, class_name, ObjectState.active, op.order.event.settings.locale)

        output_object.barcode(Barcode.qrCode, op.secret, op.secret)

        output_object.reservation_info("%s-%s" % (op.order.event.slug, op.order.code))
        output_object.ticket_holder_name(op.attendee_name or (op.addon_to.attendee_name if op.addon_to else ''))
        output_object.ticket_number(op.secret)
        output_object.ticket_type(
            get_translated_dict(
                str(op.item) + (" – " + str(op.variation.value) if op.variation else ""),
                op.order.event.settings.get('locales')
            )
        )

        places = django_settings.CURRENCY_PLACES.get(op.order.event.currency, 2)
        output_object.face_value(int(op.price * 1000 ** places), op.order.event.currency)

        if op.order.event.seating_plan_id is not None:
            if op.seat:
                output_object.seat(
                    get_translated_dict(
                        _(str(op.seat)),
                        op.order.event.settings.get('locales')
                    )
                )
            else:
                output_object.seat(
                    get_translated_dict(
                        _('General admission'),
                        op.order.event.settings.get('locales')
                    )
                )

        return self._comms().put_item(ObjectType.eventTicketObject, object_name, output_object)
