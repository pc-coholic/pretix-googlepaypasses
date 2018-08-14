import logging
import subprocess
import tempfile
import json

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile, UploadedFile
from django.utils.translation import ugettext_lazy as _
from pretix.control.forms import ClearableBasenameFileInput

logger = logging.getLogger(__name__)


def validate_json_credentials(value: str):
    value = value.strip()
    try:
        json_data = json.loads(value)
    except:
        raise ValidationError(
            _('This does not look like valid JSON data. Please copy paste the '
            'entire contents of the credentials JSON-file.'),
        )

    if not all (k in json_data for k in ("type", "project_id", "private_key_id", "private_key",
                                    "client_email", "client_id", "auth_uri", "token_uri",
                                    "auth_provider_x509_cert_url", "client_x509_cert_url")):
        raise ValidationError(
            _('It seems like the credentials-file is missing some vital information. '
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
