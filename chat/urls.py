from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("bots/<int:pk>/site/", views.site, name="site"),
    path("bots/<int:pk>/conversations/", views.conversations, name="conversations"),
    path("bots/<int:pk>/conversations/<uuid:conversation_id>/messages/", views.history, name="history"),
    path("bots/<int:pk>/messages/", views.send, name="send"),
    path("bots/<int:pk>/stop/", views.stop, name="stop"),
]
