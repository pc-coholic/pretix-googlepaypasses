import json
import logging
from json import JSONDecodeError

from django.http import (
    HttpResponse, HttpResponseBadRequest, HttpResponseForbidden,
)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pretix.base.models import Organizer

from . import tasks

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def webhook(request, *args, **kwargs):
    # Google is not actually sending their documented UA m(
    # if request.META['HTTP_USER_AGENT'] != 'Google-Valuables':
    if request.META['HTTP_USER_AGENT'] != "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)":
        return HttpResponseForbidden()

    if request.META.get('CONTENT_TYPE') != 'application/json':
        return HttpResponseBadRequest()

    try:
        webhook_json = json.loads(request.body.decode('utf-8'))
    except JSONDecodeError:
        return False

    if all(k in webhook_json for k in ('signature', 'intermediateSigningKey', 'protocolVersion', 'signedMessage')):
        organizer = Organizer.objects.filter(
            slug=request.resolver_match.kwargs['organizer'],
        ).first()

        tasks.process_webhook.apply_async(
            args=(request.body.decode('utf-8'), organizer.settings.googlepaypasses_issuer_id)
        )

    return HttpResponse()
