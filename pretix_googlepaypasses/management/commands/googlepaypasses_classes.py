from django.core.management.base import BaseCommand
from pretix.base.settings import GlobalSettingsObject
from walletobjects import ClassType
from walletobjects.comms import Comms


class Command(BaseCommand):
    help = "Query the Google Pay API for Passes for registered eventTicketClasses"

    def add_arguments(self, parser):
        parser.add_argument('action', type=str, nargs='?')
        parser.add_argument('param', type=str, nargs='?')

    def handle(self, *args, **options):
        gs = GlobalSettingsObject()
        comms = Comms(gs.settings.get('googlepaypasses_credentials'))

        if options['action'] == 'list':
            result = comms.list_items(ClassType.eventTicketClass, issuer_id=gs.settings.googlepaypasses_issuer_id)

            for resource in result['resources']:
                print(resource['id'])
        elif options['action'] == 'print':
            if not options['param']:
                print('No classID specified')
            else:
                print(comms.get_item(ClassType.eventTicketClass, options['param']))
        else:
            print('Unknown action. Use either \'list\' or \'print <classID>\'')
