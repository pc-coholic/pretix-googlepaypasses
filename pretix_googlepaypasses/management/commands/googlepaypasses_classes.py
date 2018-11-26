import json

from django.core.management.base import BaseCommand
from pretix.base.settings import GlobalSettingsObject
from pretix_googlepaypasses.googlepaypasses import WalletobjectOutput


class Command(BaseCommand):
    help = "Query the Google Pay API for Passes for registred eventticketclasses"

    def add_arguments(self, parser):
        parser.add_argument('action', type=str, nargs='?')
        parser.add_argument('param', type=str, nargs='?')

    def handle(self, *args, **options):
        gs = GlobalSettingsObject()
        authedSession = WalletobjectOutput.getAuthedSession(gs.settings)

        if options['action'] == 'list':
            result = authedSession.get(
                'https://www.googleapis.com/walletobjects/v1/eventTicketClass?issuerId=%s' % (gs.settings.googlepaypasses_issuer_id)
            )
            result = json.loads(result.text)

            for resource in result['resources']:
                print(resource['id'])
        elif options['action'] == 'print':
            if not options['param']:
                print('No classID specified')
            else:
                result = authedSession.get(
                    'https://www.googleapis.com/walletobjects/v1/eventTicketClass/%s' % (options['param'])
                )
                print(result.text)
        else:
            print('Unknown action. Use either \'list\' or \'print <classID>\'')
