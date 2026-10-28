from django.contrib import admin

from .models import Bot


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    filter_horizontal = ("allowed_users", "allowed_groups")
    fieldsets = (
        (None, {"fields": ("name", "description", "is_active")}),
        ("Dify 連線", {"fields": ("api_base_url", "api_key_env")}),
        ("使用權限", {
            "fields": ("allowed_users", "allowed_groups"),
            "description": "個人或任一群組獲授權即可使用；管理員也需獲得授權。",
        }),
    )

