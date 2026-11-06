from django.urls import path

from . import views

urlpatterns = [
	path('', views.queue, name='moderation-queue'),
	path('act/', views.act, name='moderation-act'),
	path('unban/<str:username>/', views.unban, name='moderation-unban'),
	path('unhide/<uuid:pk>/', views.unhide, name='moderation-unhide'),
]
