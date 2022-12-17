from django.apps import AppConfig
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy
from . import __version__


class GooglePayPassesApp(AppConfig):
    name = 'pretix_googlepaypasses'
    verbose_name = 'Google Pay Passes'

    class PretixPluginMeta:
        name = gettext_lazy('Google Pay Passes')
        author = 'Martin Gross'
        description = gettext_lazy('Provides Google Pay Passes for pretix')
        category = 'FORMAT'
        visible = True
        version = __version__

    def ready(self):
        from . import signals  # NOQA

    @cached_property
    def compatibility_errors(self):
        import shutil
        errs = []
        if not shutil.which('openssl'):
            errs.append("The OpenSSL binary is not installed or not in the PATH.")
        return errs

    @cached_property
    def compatibility_warnings(self):
        errs = []
        try:
            from PIL import Image  # NOQA
        except ImportError:
            errs.append("Pillow is not installed on this system, which is required for converting and scaling images.")
        return errs

default_app_config = 'pretix_googlepaypasses.GooglePayPassesApp'