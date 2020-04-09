import uuid

from django.utils import translation
from django.utils.translation import ugettext

from pretix.base.models import Event, OrderPosition
from pretix.base.settings import GlobalSettingsObject


def get_class_id(event: Event):
    gs = GlobalSettingsObject()
    if not gs.settings.get('update_check_id'):
        gs.settings.set('update_check_id', uuid.uuid4().hex)

    issuer_id = event.settings.get('googlepaypasses_issuer_id')

    return "%s.pretix-%s-%s-%s" % (issuer_id, gs.settings.get('update_check_id'), event.organizer.slug, event.slug)


def get_object_id(op: OrderPosition):
    gs = GlobalSettingsObject()
    if not gs.settings.get('update_check_id'):
        gs.settings.set('update_check_id', uuid.uuid4().hex)

    issuer_id = op.order.event.settings.get('googlepaypasses_issuer_id')

    return "%s.pretix-%s-%s-%s-%s-%s-%s" % (issuer_id, gs.settings.get('update_check_id'),
                                            op.order.event.organizer.slug, op.order.event.slug,
                                            op.order.code, op.positionid, uuid.uuid4().hex)


def get_translated_dict(string, locales):
    translated = {}

    for locale in locales:
        translation.activate(locale)
        translated[locale] = ugettext(string)
        translation.deactivate()

    return translated


def get_translated_string(string, locale):
    translation.activate(locale)
    translated = ugettext(string)
    translation.deactivate()

    return translated
