from django.conf.urls import url
from pretix.multidomain import event_url

from .views import GeoCodeView, redirectToWalletObjectJWT, webhook

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/googlepaypasses/geocode/$',
        GeoCodeView.as_view(),
        name='geocode'),
    url(r'^_googlepaypasses/webhook/$', webhook, name='webhook'),
]

event_patterns = [
    event_url(r'^order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<position>[0-9]+)/googlepaypasses/generate$',
              redirectToWalletObjectJWT.as_view(),
              name='generatewalletobject',
              require_live=True),
]
