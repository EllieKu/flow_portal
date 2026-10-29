from django.conf import settings
from django.core.validators import URLValidator
from django.db import models
from django.urls import reverse


class Bot(models.Model):
    name = models.CharField("名稱", max_length=100)
    description = models.TextField("說明", blank=True)
    is_active = models.BooleanField("啟用", default=True)
    api_base_url = models.URLField(
        "Dify API 網址",
        default="https://api.dify.ai/v1",
        validators=[URLValidator(schemes=["https", "http"])],
        help_text="填入應用的 API base URL，例如 https://api.dify.ai/v1。",
    )
    api_key = models.TextField(
        "Dify API Key",
        blank=True,
        default="",
        help_text="填入 Dify 應用金鑰；編輯時留白保留原本金鑰。",
    )
    allowed_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name="授權使用者",
        blank=True,
        related_name="granted_bots",
    )
    allowed_groups = models.ManyToManyField(
        "auth.Group",
        verbose_name="授權群組",
        blank=True,
        related_name="granted_bots",
    )

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Bot"
        verbose_name_plural = "Bot"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("bots:chat", args=[self.pk])

