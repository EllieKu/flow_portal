from django import forms
from django.contrib import admin
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters

from .models import Bot


class BotAdminForm(forms.ModelForm):
    api_key = forms.CharField(
        label="Dify API Key",
        required=False,
        strip=True,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}, render_value=False),
        help_text="新增時填入應用金鑰；編輯時留白保留原本金鑰，輸入新值則替換。",
    )

    class Meta:
        model = Bot
        fields = "__all__"

    def clean_api_key(self):
        key = self.cleaned_data.get("api_key") or self.instance.api_key
        if not key:
            raise forms.ValidationError("請填寫 Dify 應用 API Key。")
        return key


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    form = BotAdminForm
    list_display = ("name", "is_active", "has_api_key")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    filter_horizontal = ("allowed_users", "allowed_groups")
    fieldsets = (
        (None, {"fields": ("name", "description", "is_active")}),
        ("Dify 連線", {"fields": ("api_base_url", "api_key")}),
        ("使用權限", {
            "fields": ("allowed_users", "allowed_groups"),
            "description": "個人或任一群組獲授權即可使用；管理員也需獲得授權。",
        }),
    )

    @admin.display(boolean=True, description="已設定金鑰")
    def has_api_key(self, obj):
        return bool(obj.api_key)

    @method_decorator(sensitive_post_parameters("api_key"))
    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        return super().changeform_view(request, object_id, form_url, extra_context)

