from django.contrib import admin

from .models import Device


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "status", "assigned_patient", "created_at")
    list_filter = ("status", "assigned_patient", "created_at")
    search_fields = ("name", "owner__username", "assigned_patient__full_name")
    readonly_fields = ("id", "created_at")
    autocomplete_fields = ("owner", "assigned_patient")
