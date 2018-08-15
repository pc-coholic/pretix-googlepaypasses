import tempfile
from collections import OrderedDict
from typing import Tuple
import uuid
import json

import pytz
from django import forms
from django.core.files.storage import default_storage
from django.template.loader import get_template
from django.utils.translation import ugettext, ugettext_lazy as _
from pretix.base.models import OrderPosition
from pretix.base.ticketoutput import BaseTicketOutput
from pretix.multidomain.urlreverse import build_absolute_uri, eventreverse
from pretix.base.settings import GlobalSettingsObject

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
        if not gs.settings.update_check_id:
            gs.settings.set('update_check_id', uuid.uuid4().hex)

        issuerId = order.event.settings.get('googlepaypasses_issuer_id')

        return "%s.pretix-%s-%s-%s" % (issuerId, gs.settings.update_check_id, order.event.organizer.slug, order.event.slug)

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
        eventticketclassName = WalletobjectOutput.constructClassName(order)

        eventticket_class = {
            'kind': 'walletobjects#eventTicketClass',
            'id': eventticketclassName,
            'issuerName': order.event.organizer.name,
        }

        # TODO: I18n
        eventticket_class['localizedIssuerName'] = {
            'kind': 'walletobjects#localizedString',
            'translatedValues': [{
                'kind': 'walletobjects#translatedString',
                'language': 'FIXME',
                'value': 'FIXME'
            }],
            'defaultValue': {
                'kind': 'walletobjects#translatedString',
                'language': 'FIXME',
                'value': 'FIXME'
            }
        }

        # Not used at this moment
        # Up to 10 messages can be placed
        '''
        eventticket_class['messages'] = [{
            'kind': 'walletobjects#walletObjectMessage',
            'header': 'String',
            'localizedHeader': {
                'kind': 'walletobjects#localizedString',
                'translatedValues': [{
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'String'
                }],
                'defaultValue': {
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'String'
                }
            },
            'body': 'String',
            'localizedBody': {
                'kind': 'walletobjects#localizedString',
                'translatedValues': [{
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'String'
                }],
                'defaultValue': {
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'String'
                }
            },
            'displayInterval': {
                'kind': 'walletobjects#timeInterval',
                'start': {
                    'date': '1985-04-12T23:20:50.52Z'
                },
                'end': {
                    'date': '1985-04-12T25:20:50.52Z'
                }
            },
            'id': 'UUID',
            'messageType': 'expirationNotification' or 'text'
        }]
        '''

        # TODO: I18n
        eventticket_class['homepageUri'] = {
            'kind': 'walletobjects#uri',
            'uri': 'FIXME',
            'description': 'FIXME',
            'localizedDescription': {
                'kind': 'walletobjects#localizedString',
                'translatedValues': [{
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'FIXME'
                }],
                'defaultValue': {
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'FIXME'
                }
            }
        }

        if (order.event.settings.ticketoutput_googlepaypasses_latitude
                and order.event.settings.ticketoutput_googlepaypasses_longitude):
            eventticket_class['locations'] = [{
                'kind': 'walletobjects#latLongPoint',
                'latitude': order.event.settings.ticketoutput_googlepaypasses_latitude,
                'longitude': order.event.settings.ticketoutput_googlepaypasses_longitude
            }]

        # TODO: Proper state machine handling
        eventticket_class['reviewStatus'] = 'draft' # 'draft' || 'underReview' || 'approved' || 'rejected'

        # Not used at this moment
        '''
        eventticket_class['infoModuleData']: {
            'labelValueRows': [{
                'columns': [{
                    'label': 'String',
                    'localizedLabel': {
                        'kind': 'walletobjects#localizedString',
                        'translatedValues': [{
                            'kind': 'walletobjects#translatedString',
                            'language': 'de_DE',
                            'value': 'FIXME'
                        }],
                        'defaultValue': {
                            'kind': 'walletobjects#translatedString',
                            'language': 'de_DE',
                            'value': 'FIXME'
                        }
                    },
                    'value': 'String',
                    'localizedLabel': {
                        'kind': 'walletobjects#localizedString',
                        'translatedValues': [{
                            'kind': 'walletobjects#translatedString',
                            'language': 'de_DE',
                            'value': 'FIXME'
                        }],
                        'defaultValue': {
                            'kind': 'walletobjects#translatedString',
                            'language': 'de_DE',
                            'value': 'FIXME'
                        }
                    }
                }]
            }]
        }
        '''

        # Not used at this moment
        # Even though this is an array, only 1 image can be placed
        '''
        eventticket_class['imageModulesData'] = [{
            'mainImage': {
                'kind': 'walletobjects#image',
                'sourceUri': {
                    'kind': 'walletobjects#uri',
                    'uri': 'String',
                    'description': 'String',
                    'localizedDescription': {
                        'kind': 'walletobjects#localizedString',
                        'translatedValues': [{
                            'kind': 'walletobjects#translatedString',
                            'language': 'de_DE',
                            'value': 'FIXME'
                        }],
                        'defaultValue': {
                            'kind': 'walletobjects#translatedString',
                            'language': 'de_DE',
                            'value': 'FIXME'
                        }
                    }
                }
            }
        }]
        '''

        # Not used at this moment
        # Up to 10 textmodules can be placed
        '''
        eventticket_class['textModulesData'] = [{
            'header': 'String',
            'body': 'String',
            'localizedHeader': {
                'kind': 'walletobjects#localizedString',
                'translatedValues': [{
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'String'
                }],
                'defaultValue': {
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'String'
                }
            },
            'localizedBody': {
                'kind': 'walletobjects#localizedString',
                'translatedValues': [{
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'String'
                }],
                'defaultValue': {
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'String'
                }
            }
        }]
        '''

        # TODO: I18n
        # Up to 10 linkmodules can be placed
        eventticket_class['linksModuleData'] = {
            'uris': [{
                'kind': 'walletobjects#uri',
                'uri': 'mailto:%s' % order.event.settings.mail_from,
                'description': order.event.settings.mail_from,
                'localizedDescription': {
                    'kind': 'walletobjects#localizedString',
                    'translatedValues': [{
                        'kind': 'walletobjects#translatedString',
                        'language': 'de_DE',
                        'value': 'FIXME'
                    }],
                    'defaultValue': {
                        'kind': 'walletobjects#translatedString',
                        'language': 'de_DE',
                        'value': 'FIXME'
                    }
                }
            }]
        }

        eventticket_class['countryCode'] = 'FIXME' # TODO: de_DE or DE?
        eventticket_class['hideBarcode'] = False

        # TODO: Proper URL concat
        # TODO: I18n
        if order.event.settings.ticketoutput_googlepaypasses_hero:
            #print(order.event.settings.ticketoutput_googlepaypasses_hero.url)
            #print(build_absolute_uri(order.event, ''))
            eventticket_class['heroImage'] = {
                "kind": "walletobjects#image",
                "sourceUri": {
                    "kind": "walletobjects#uri",
                    "uri": 'https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png',
                    #"description": 'String',
                    'localizedDescription': {
                        'kind': 'walletobjects#localizedString',
                        'translatedValues': [{
                            'kind': 'walletobjects#translatedString',
                            'language': 'de_DE',
                            'value': 'FIXME'
                        }],
                        'defaultValue': {
                            'kind': 'walletobjects#translatedString',
                            'language': 'de_DE',
                            'value': 'FIXME'
                        }
                    }
                }
            }

        eventticket_class['hexBackgroundColor'] = 'FIXME' # TODO: get from settings
        eventticket_class['multipleDevicesAndHoldersAllowedStatus'] = 'FIXME' # 'multipleHolders' || 'oneUserAllDevices' # TODO: Implement Setting

        # TODO: I18n
        eventticket_class['eventName'] = {
            'kind': 'walletobjects#localizedString',
            'translatedValues': [{
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }],
            'defaultValue': {
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }

        }

        eventticket_class['eventId'] = 'UUID' # TODO: Use Main-Event UUID/constructClassName

        # TODO: Proper URL concat
        # TODO: I18n
        if order.event.settings.ticketoutput_googlepaypasses_logo:
            #print(order.event.settings.ticketoutput_googlepaypasses_logo.url)
            #print(build_absolute_uri(order.event, ''))
            eventticket_class['logo'] = {
                "kind": "walletobjects#image",
                "sourceUri": {
                    "kind": "walletobjects#uri",
                    "uri": 'https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png',
                    #"description": 'String',
                    'localizedDescription': {
                        'kind': 'walletobjects#localizedString',
                        'translatedValues': [{
                            'kind': 'walletobjects#translatedString',
                            'language': 'de_DE',
                            'value': 'FIXME'
                        }],
                        'defaultValue': {
                            'kind': 'walletobjects#translatedString',
                            'language': 'de_DE',
                            'value': 'FIXME'
                        }
                    }
                }
            }

        # TODO: I18n
        eventticket_class['venue'] = {
            'kind': 'walletobjects#eventVenue',
            'name': {
                'kind': 'walletobjects#localizedString',
                'translatedValues': [{
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'FIXME'
                }],
                'defaultValue': {
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'FIXME'
                }
            },
            'address': {
                'kind': 'walletobjects#localizedString',
                'translatedValues': [{
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'FIXME'
                }],
                'defaultValue': {
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'FIXME'
                }
            }
        }

        # TODO: I18n
        # TODO: check if set
        # Either doorsOpenLabel or customDoorsOpenLabel
        eventticket_class['dateTime'] = {
            'kind': 'walletobjects#eventDateTime',
            'doorsOpenLabel': 'doorsOpen', # 'doorsOpen' || 'gatesOpen'
            '''
            'customDoorsOpenLabel': {
                'kind': 'walletobjects#localizedString',
                'translatedValues': [{
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'FIXME'
                }],
                'defaultValue': {
                    'kind': 'walletobjects#translatedString',
                    'language': 'de_DE',
                    'value': 'FIXME'
                }
            },
            '''
            'doorsOpen': '1985-04-12T23:20:50.52Z ',
            'start': '1985-04-12T23:20:50.52Z ',
            'end': '1985-04-12T25:20:50.52Z '
        }

        # Not used at this moment
        '''
        eventticket_class['finePrint']: {
            'kind': 'walletobjects#localizedString',
            'translatedValues': [{
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }],
            'defaultValue': {
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }
        }
        '''

        # Either confirmationCodeLabel or customConfirmationCodeLabel
        eventticket_class['confirmationCodeLabel'] = 'orderNumber' # 'confirmationCode' || 'confirmationNumber' || 'orderNumber' || 'reservationNumber'

        # Not used at this moment
        '''
        eventticket_class['customConfirmationCodeLabel'] = {
            'kind': 'walletobjects#localizedString',
            'translatedValues': [{
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }],
            'defaultValue': {
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }
        }
        '''

        # Not used at this moment
        # Either seatLabel or customSeatLabel
        #eventticket_class['seatLabel'] = 'seat'

        # Not used at this moment
        '''
        eventticket_class['customSeatLabel'] = {
            'kind': 'walletobjects#localizedString',
            'translatedValues': [{
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }],
            'defaultValue': {
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }
        }
        '''

        # Not used at this moment
        # Either rowLabel or customRowLabel
        #eventticket_class['rowLabel'] = 'row'

        # Not used at this moment
        '''
        eventticket_class['customRowLabel'] = {
            'kind': 'walletobjects#localizedString',
            'translatedValues': [{
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }],
            'defaultValue': {
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }
        }
        '''

        # Not used at this moment
        # Either sectionLabel or customSectionLabel
        #eventticket_class['sectionLabel'] = 'section' || 'theater'

        # Not used at this moment
        '''
        eventticket_class['customSectionLabel'] = {
            'kind': 'walletobjects#localizedString',
            'translatedValues': [{
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }],
            'defaultValue': {
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }
        }
        '''

        # Not used at this moment
        # Either gateLabel or customGateLabel
        #eventticket_class['gateLabel'] = 'door' || 'entrance' || 'gate'

        # Not used at this moment
        '''
        eventticket_class['customGateLabel'] = {
            'kind': 'walletobjects#localizedString',
            'translatedValues': [{
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }],
            'defaultValue': {
                'kind': 'walletobjects#translatedString',
                'language': 'de_DE',
                'value': 'FIXME'
            }
        }
        '''

        #print(eventticket_class)
