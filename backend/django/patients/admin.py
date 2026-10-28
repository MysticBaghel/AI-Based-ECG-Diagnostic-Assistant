from django.contrib import admin

from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("patient_id", "full_name", "phone", "age", "sex", "created_at")
    search_fields = ("patient_id", "full_name", "phone", "email")
    list_filter = ("sex", "created_at")
    readonly_fields = ("patient_id", "phone_normalized", "created_at", "updated_at")
    ordering = ("-created_at",)

    @admin.display(description="Age")
    def age(self, obj):
        years = obj.age
        return "—" if years is None else years
