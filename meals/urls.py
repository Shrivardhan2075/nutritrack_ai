from django.urls import path

from . import views

app_name = "meals"

urlpatterns = [
    path("go/", views.dashboard_redirect, name="dashboard_redirect"),
    path("upload/", views.upload_view, name="upload"),
    path("result/<int:meal_id>/", views.result_view, name="result"),
    path("adjust/<int:meal_id>/", views.adjust_portions_view, name="adjust_portions"),
    path("add/<int:meal_id>/", views.add_item_view, name="add_item"),
    path("delete/<int:meal_id>/<int:item_id>/", views.delete_item_view, name="delete_item"),
    path("history/", views.history_view, name="history"),
]
