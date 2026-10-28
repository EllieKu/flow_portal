import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    dify_user_id = models.UUIDField(
        "Dify 使用者識別",
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="建立帳號時產生，與帳號名稱及 Email 無關。",
    )

