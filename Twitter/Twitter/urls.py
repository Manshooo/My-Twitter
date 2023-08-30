from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path, re_path
from django.conf.urls.static import static
from django.conf import settings

from .views import index, PostListView, UserProfileDetailView, my_view


urlpatterns = [
	path('', index, name='index'),
	path('', PostListView.as_view(), name='post'),
	path('admin/', admin.site.urls),
	path("auth/", include('customUser.urls')),
	path('auth/', include('django.contrib.auth.urls')),
	path('my-api/', my_view, name='my-api'),
	path('users/<str:slug>/', login_required(UserProfileDetailView.as_view()), name='user_profile'),
	
]
if settings.DEBUG:
	urlpatterns += path("__debug__/", include("debug_toolbar.urls")),
	urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)