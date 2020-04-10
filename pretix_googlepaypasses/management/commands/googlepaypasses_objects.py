
from django.core.management.base import BaseCommand
from pretix.base.settings import GlobalSettingsObject
from walletobjects import EventTicketObject
from walletobjects.comms import Comms
from walletobjects.constants import ObjectState, ObjectType


class Command(BaseCommand):
    help = "Query the Google Pay API for Passes for registered eventTicketObjects"

    def add_arguments(self, parser):
        parser.add_argument('action', type=str, nargs='?')
        parser.add_argument('param', type=str, nargs='?')

    def handle(self, *args, **options):
        gs = GlobalSettingsObject()
        comms = Comms(gs.settings.get('googlepaypasses_credentials'))

        if options['action'] == 'list':
            if not options['param']:
                print('No classID specified')
            else:
                result = comms.list_items(ObjectType.eventTicketObject, class_id=options['param'])

                for resource in result['resources']:
                    print('%s - hasUsers: %r - state: %r' % (resource['id'], resource['hasUsers'], resource['state']))
        elif options['action'] == 'print':
            if not options['param']:
                print('No objectID specified')
            else:
                print(comms.get_item(ObjectType.eventTicketObject, options['param']))
        elif options['action'] == 'shred':
            if not options['param']:
                print('No objectID specified')
            else:
                item = comms.get_item(ObjectType.eventTicketObject, options['param'])

                if not item:
                    print('Could not retrieve object %s' % (options['param']))
                    return

                class_id = item['class_id']

                output_object = EventTicketObject(options['param'], class_id, ObjectState.inactive, 'EN')

                if not comms.put_item(ObjectType.eventTicketObject, options['param'], output_object):
                    print('Something went wrong when shredding the object %s' % options['param'])
                else:
                    print('Successfully shredded object %s' % (options['param']))
        else:
            print('Unknown action. Use either \'list <classID>\', \'print <objectID>\' or \'shred <objectID>\'')
