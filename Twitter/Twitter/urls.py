from django.contrib import admin
from django.urls import include, path, re_path
from django.conf.urls.static import static
from django.conf import settings

from .views import index, PostListView, TestListView, my_view

urlpatterns = [
	path('', index, name='index'),
	path('', PostListView.as_view(), name='post'),
	path('admin/', admin.site.urls),
	path('test', TestListView.as_view(), name='test'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('my-api/', my_view, name='my-api'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
