from django.urls import path

from . import views

urlpatterns = [
	path('', views.inbox_page, name='dm-inbox'),
	path('new/<str:username>/', views.start, name='dm-start'),
	path('<int:pk>/', views.conversation_page, name='dm-conversation'),
	path('<int:pk>/updates/', views.conversation_updates, name='dm-updates'),
	path('<int:pk>/send/', views.send, name='dm-send'),
	path('<int:pk>/clear/', views.clear, name='dm-clear'),
	path('<int:pk>/m/<int:message_id>/delete/', views.delete_message, name='dm-delete'),
]
