import json
import logging
from json import JSONDecodeError

from pretix.base.views.tasks import AsyncAction
from django.http import (
    Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden,
    JsonResponse,
)
from django.utils.translation import ugettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from googlemaps import Client
from googlemaps.exceptions import ApiError
from pretix.base.models import Organizer
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.presale.views.order import OrderDetailMixin

from . import tasks

logger = logging.getLogger(__name__)


class GeoCodeView(EventPermissionRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        c = Client(key=request.event.settings.get('passbook_gmaps_api_key'))
        try:
            r = c.geocode(address=request.event.location, language=request.LANGUAGE_CODE.split("_")[0])
        except ApiError:
            logger.exception('Google Maps API Error')
            return JsonResponse({
                'status': 'error',
            })
        else:
            return JsonResponse({
                'status': 'ok',
                'result': r
            })


class redirectToWalletObjectJWT(OrderDetailMixin, AsyncAction, View):
    task = tasks.generateWalletObjectJWT

    def get_success_url(self, value):
        return 'https://pay.google.com/gp/v/save/%s' % value

    def get_error_url(self):
        return self.get_order_url()

    def post(self, request, *args, **kwargs):
        if not self.order:
            raise Http404(_('Unknown order code or not authorized to access this order.'))

        return self.do(self.order.id, kwargs['position'])

    def get_error_message(self, exception):
        return _("An error occured while generating your Google Pay Pass. Please try again later.")


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
        webhook_json = json.loads(request.body)
    except JSONDecodeError:
        return False

    if all(k in webhook_json for k in ('signature', 'intermediateSigningKey', 'protocolVersion', 'signedMessage')):
        organizer = Organizer.objects.filter(
            slug=request.resolver_match.kwargs['organizer'],
        ).first()

        tasks.procesWebhook.apply_async(args=(request.body, organizer.settings.googlepaypasses_issuer_id))

    return HttpResponse()
