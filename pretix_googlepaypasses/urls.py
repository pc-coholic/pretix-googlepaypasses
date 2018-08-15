from django.conf.urls import url
from pretix.multidomain import event_url

from . import views

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/passbookoutput/geocode/$',
        views.GeoCodeView.as_view(),
        name='geocode'),
    event_url(r'^(?P<organizer>[^/]+)/(?P<event>[^/]+)/order/(?P<order>[^/]+)/(?P<secret>[A-Za-z0-9]+)/download/(?P<position>[0-9]+)/googlepaypasses/generate$',
        views.generateWalletObject,
        name='generatewalletobject',
        require_live=True),
]
