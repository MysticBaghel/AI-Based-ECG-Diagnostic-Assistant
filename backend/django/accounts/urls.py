from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LoginView, MeView, PatientProfileViewSet

router = DefaultRouter()
router.register("patients", PatientProfileViewSet, basename="patient")

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("", include(router.urls)),
]
