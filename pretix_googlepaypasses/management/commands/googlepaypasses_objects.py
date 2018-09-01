from django.core.management.base import BaseCommand
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from pretix.base.settings import GlobalSettingsObject
from pretix_googlepaypasses.googlepaypasses import WalletobjectOutput
from walletobjects import eventTicketObject
from walletobjects.constants import objectState
import json

class Command(BaseCommand):
    help = "Query the Google Pay API for Passes for registred eventticketobjects"

    def add_arguments(self, parser):
        parser.add_argument('action', type=str, nargs='?')
        parser.add_argument('param', type=str, nargs='?')

    def handle(self, *args, **options):
        gs = GlobalSettingsObject()
        authedSession = WalletobjectOutput.getAuthedSession(gs.settings)

        if options['action'] == 'list':
            if not options['param']:
                print('No classID specified')
            else:
                result = authedSession.get(
                    'https://www.googleapis.com/walletobjects/v1/eventTicketObject?classId=%s' % (options['param'])
                )
                result = json.loads(result.text)

                for resource in result['resources']:
                    print('%s - hasUsers: %r - state: %r' % (resource['id'], resource['hasUsers'], resource['state']))
        elif options['action'] == 'print':
            if not options['param']:
                print('No objectID specified')
            else:
                result = authedSession.get(
                    'https://www.googleapis.com/walletobjects/v1/eventTicketObject/%s' % (options['param'])
                )
                print(result.text)
        elif options['action'] == 'shred':
            if not options['param']:
                print('No objectID specified')
            else:
                evTobject = authedSession.get(
                    'https://www.googleapis.com/walletobjects/v1/eventTicketObject/%s' % (options['param'])
                )
                if not evTobject.status_code == 200:
                    print('Could not retrieve object %s' % (options['param']))
                    return

                evTobject = json.loads(evTobject.text)
                classId = evTobject['classId']

                evTobject = eventTicketObject(options['param'], classId, objectState.inactive, 'EN')

                result = authedSession.put(
                    'https://www.googleapis.com/walletobjects/v1/eventTicketObject/%s?strict=true' % options['param'],
                    json=json.loads(str(evTobject))
                )

                if not result.status_code == 200:
                    print('Something went wrong when shredding the object %s\n\n%s' % (options['param'], result.text))
                else:
                    print('Successfully shredded object %s' % (options['param']))
        else:
            print('Unknown action. Use either \'list <classID>\', \'print <objectID>\' or \'shred <objectID>\'')
