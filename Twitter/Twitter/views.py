from django.http import response
from django.shortcuts import render
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from rest_framework.views import APIView, status
from django.contrib.auth.decorators import login_required


from .models import Post, Profile
from .serializers import PostSerializer

def index(request):
	latest_posts = Post.objects.order_by("-created_at")[:10]
	context = {"latest_posts": latest_posts}
	return render(request, "twitter/twitter_indexPage.html", context)

@login_required()
def create_post(request):
	if request.method == 'POST':
		user = request.user.username
		text = request.POST['text']

		new_post = Post.objects.create(user=user, text=text)
		new_post.save()
	else:
		pass
class UserProfileDetailView(DetailView):
	template_name = "registration/profile.html"
	model = Profile
	context_object_name = "profile"
	pk_url_kwarg = "username"
	slug_field = "user__username"
	
	def	get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		profile_posts = Post.objects.filter(author=self.get_object())
		context["profile_posts"] = profile_posts
		return context
class PostListView(ListView):
	template_name = "twitter/twitter_post.html"
	model = Post
	context_object_name = "posts"

class PostListAPIView(APIView):
	def get(self, request, id):
		posts = Post.objects.filter(author=id)
		serializer = PostSerializer(posts, many=True)
		return response({"data": serializer.data}, status=status.HTTP_200_OK)