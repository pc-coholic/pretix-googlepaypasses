from django.urls import re_path
from pretix_googlepaypasses.views import webhook

urlpatterns = [
    re_path(r'^_googlepaypasses/webhook/(?P<organizer>[^/]+)/$', webhook, name='webhook'),
]
