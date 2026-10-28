from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("report_id", "patient", "session", "version", "file_size", "generated_at")
    list_filter = ("generated_at",)
    search_fields = ("report_id", "patient__full_name", "patient__patient_id", "session__id")
    readonly_fields = (
        "report_id",
        "session",
        "patient",
        "version",
        "analysis_snapshot",
        "file_size",
        "checksum",
        "generated_at",
        "generated_by",
    )

    def has_add_permission(self, request):
        return False
