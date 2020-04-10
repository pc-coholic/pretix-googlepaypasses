import json
import logging
import tempfile

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile, UploadedFile
from django.utils.translation import ugettext_lazy as _
from google.oauth2 import service_account
from pretix.control.forms import ClearableBasenameFileInput

logger = logging.getLogger(__name__)


def validate_json_credentials(value: str):
    value = value.strip()
    try:
        service_account.Credentials.from_service_account_info(
            json.loads(value),
            scopes=['https://www.googleapis.com/auth/wallet_object.issuer'],
        )
    except ValueError:
        raise ValidationError(
            _('It seems like the credentials-file is not correct. '
              'Please make sure that you pasted the entire contents of the file.'),
        )


class PNGImageField(forms.FileField):
    widget = ClearableBasenameFileInput

    def clean(self, value, *args, **kwargs):
        value = super().clean(value, *args, **kwargs)
        if isinstance(value, UploadedFile):
            try:
                from PIL import Image
            except ImportError:
                return value

            value.open('rb')
            value.seek(0)
            try:
                with Image.open(value) as im, tempfile.NamedTemporaryFile('rb', suffix='.png') as tmpfile:
                    im.save(tmpfile.name)
                    tmpfile.seek(0)
                    return SimpleUploadedFile('picture.png', tmpfile.read(), 'image png')
            except IOError:
                logger.exception('Could not convert image to PNG.')
                raise ValidationError(
                    _('The file you uploaded could not be converted to PNG format.')
                )

        return value
