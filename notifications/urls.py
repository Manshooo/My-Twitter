from django.urls import path

from .views import notifications_page, unread_badge

urlpatterns = [
	path('', notifications_page, name='notifications'),
	path('unread/', unread_badge, name='notifications-unread'),
]
