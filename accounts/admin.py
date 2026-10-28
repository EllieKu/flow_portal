from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class PortalUserAdmin(UserAdmin):
    readonly_fields = (*UserAdmin.readonly_fields, "dify_user_id")
    fieldsets = (
        *UserAdmin.fieldsets,
        ("Dify", {"fields": ("dify_user_id",)}),
    )


admin.site.site_header = "Flow Portal 管理後台"
admin.site.site_title = "Flow Portal"
admin.site.index_title = "管理"

