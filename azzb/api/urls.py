from django.contrib.auth.decorators import login_required
from django.urls import path

from .views import *

from post.views import like, delete

urlpatterns = [
	path('new-post/', login_required(create_post), name='create_post_api'),
	path('profiles/', profiles_list, name='profiles_list'),
	path('profiles/<int:pk>/', profile_details, name='profile_details'),
	#path('post/', login_required(PostAPIView.as_view()), name='create_post_api')
	path('like-post/', login_required(like), name='like_post_api'),
	path('delete-post/', login_required(delete), name='delete_post_api')
]
