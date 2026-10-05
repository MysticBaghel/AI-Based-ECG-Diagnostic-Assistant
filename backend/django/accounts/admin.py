from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import DoctorAssignment, DoctorProfile, PatientProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin for the custom user model.

    Reuses Django's UserAdmin (password hashing, permission widgets) and adds
    the role field to the list and to the edit forms.
    """

    list_display = ("username", "email", "role")
    list_filter = ("role", "is_staff", "is_active")

    fieldsets = BaseUserAdmin.fieldsets + (
        ("Role", {"fields": ("role",)}),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Role", {"fields": ("role",)}),
    )


class DoctorAssignmentInline(admin.TabularInline):
    """Assign patients straight from the doctor's page."""

    model = DoctorAssignment
    extra = 0
    autocomplete_fields = ("patient",)
    readonly_fields = ("created_at",)


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "speciality")
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user",)
    # The M2M has a through model, so it is read-only by design; the inline
    # below is how assignments are actually created and removed.
    exclude = ("patients",)
    inlines = (DoctorAssignmentInline,)


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "date_of_birth")
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user",)


@admin.register(DoctorAssignment)
class DoctorAssignmentAdmin(admin.ModelAdmin):
    list_display = ("doctor", "patient", "created_at")
    list_filter = ("doctor", "created_at")
    autocomplete_fields = ("doctor", "patient")
    readonly_fields = ("created_at",)
