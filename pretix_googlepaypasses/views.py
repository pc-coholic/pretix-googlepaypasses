import json
import logging
from json import JSONDecodeError

from django.http import HttpResponseRedirect, JsonResponse, HttpResponseForbidden, HttpResponseBadRequest, HttpResponse, \
    Http404
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from googlemaps import Client
from googlemaps.exceptions import ApiError

from base.views.tasks import AsyncAction
from pretix.control.permissions import EventPermissionRequiredMixin
from pretix.presale.views.order import OrderDetailMixin
from django.utils.translation import ugettext_lazy as _

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
    if request.META['HTTP_USER_AGENT'] != 'Google-Valuables':
        return HttpResponseForbidden()

    if request.META.get('HTTP_ACCEPT') != 'application/json':
        return HttpResponseBadRequest()

    try:
        webhook_json = json.loads(request.body.decode('utf-8'))
        print(webhook_json)
    except JSONDecodeError:
        return HttpResponseBadRequest()

    # https://developers.google.com/pay/passes/guides/overview/how-to/use-callbacks#expected-message-format
    # Worker: Check signature
    # Worker: Process
    return HttpResponse()
