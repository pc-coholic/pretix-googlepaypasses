from django.conf.urls import url
from pretix_googlepaypasses.views import webhook

urlpatterns = [
    url(r'^_googlepaypasses/webhook/(?P<organizer>[^/]+)/$', webhook, name='webhook'),
]
