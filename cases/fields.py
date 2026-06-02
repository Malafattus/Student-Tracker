import logging

from django.db import models

from .crypto import decrypt_text, encrypt_text

logger = logging.getLogger(__name__)
UNREADABLE_ENCRYPTED_VALUE = "[Protected value unavailable. Check encryption keys.]"


class EncryptedTextField(models.TextField):
    description = "Text field encrypted at rest"

    def from_db_value(self, value, expression, connection):
        try:
            return decrypt_text(value)
        except Exception:
            logger.exception("Could not decrypt protected text from the database.")
            return UNREADABLE_ENCRYPTED_VALUE

    def to_python(self, value):
        value = super().to_python(value)
        try:
            return decrypt_text(value)
        except Exception:
            logger.exception("Could not decrypt protected text during form conversion.")
            return UNREADABLE_ENCRYPTED_VALUE

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value == UNREADABLE_ENCRYPTED_VALUE:
            return value
        return encrypt_text(value)
