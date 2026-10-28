from django.contrib import admin

from .models import Session, SessionAnalysis


class SessionAnalysisInline(admin.StackedInline):
    model = SessionAnalysis
    extra = 0
    can_delete = False
    readonly_fields = ("status", "model_version", "analyzed_at", "error", "result")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "device", "status", "start_time", "end_time")
    list_filter = ("status", "start_time")
    search_fields = ("id", "patient__full_name", "patient__patient_id", "device__name")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("patient", "device")
    inlines = (SessionAnalysisInline,)


@admin.register(SessionAnalysis)
class SessionAnalysisAdmin(admin.ModelAdmin):
    list_display = ("session", "status", "model_version", "analyzed_at")
    list_filter = ("status",)
    search_fields = ("session__id", "session__patient__full_name")
    readonly_fields = ("analyzed_at", "updated_at")
