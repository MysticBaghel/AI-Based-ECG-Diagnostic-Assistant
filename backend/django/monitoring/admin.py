from django.contrib import admin

from .models import Session


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "device",
        "started_by",
        "status",
        "start_time",
        "end_time",
    )
    list_filter = ("status", "start_time")
    search_fields = ("patient__user__username", "device__name", "started_by__username")
    readonly_fields = ("id", "start_time")
    autocomplete_fields = ("patient", "device", "started_by")
