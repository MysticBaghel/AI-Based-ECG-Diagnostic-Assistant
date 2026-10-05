from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    """Liveness probe used by the frontend to check the backend is up."""
    return JsonResponse({"status": "ok", "service": "django"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    # Each app owns its own routes; they are all mounted under /api/.
    path("api/", include("accounts.urls")),
    path("api/", include("devices.urls")),
    path("api/", include("monitoring.urls")),
]
