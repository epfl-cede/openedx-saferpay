from django.urls import path
from . import views

urlpatterns = [
    path("completed/success/<int:ppr_id>/", views.SaferpaySuccessCallbackView.as_view(), name="callback_success"),
]
