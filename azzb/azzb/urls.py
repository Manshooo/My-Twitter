from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path, re_path
from django.conf.urls.static import static
from django.conf import settings

from .views import index
from customUser.views import UserProfileDetailView

urlpatterns = [
	path('', index, name='index'),
	path('admin/', admin.site.urls),
	path('auth/', include('customUser.urls')),
	path('auth/', include('django.contrib.auth.urls')),
	path('users/<str:slug>/', login_required(UserProfileDetailView.as_view()), name='profile'),
	path('api/', include('api.urls')),
]
if settings.DEBUG:
	urlpatterns += path("__debug__/", include("debug_toolbar.urls")),
	urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_URL)
	urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)