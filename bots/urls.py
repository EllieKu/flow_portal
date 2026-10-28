from django.urls import path

from . import views

app_name = "bots"

urlpatterns = [
    path("", views.bot_list, name="list"),
    path("<int:pk>/chat/", views.bot_chat, name="chat"),
]

