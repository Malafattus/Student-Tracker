from django.db import models

from .crypto import decrypt_text, encrypt_text


class EncryptedTextField(models.TextField):
    description = "Text field encrypted at rest"

    def from_db_value(self, value, expression, connection):
        return decrypt_text(value)

    def to_python(self, value):
        value = super().to_python(value)
        return decrypt_text(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt_text(value)
