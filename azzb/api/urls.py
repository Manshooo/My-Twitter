from django.contrib.auth.decorators import login_required
from django.urls import path

from .views import create_post
#from .views import PostAPIView

urlpatterns = [
	path('new-post/', login_required(create_post), name='create_post_api')
	#path('post/', login_required(PostAPIView.as_view()), name='create_post_api')
]
