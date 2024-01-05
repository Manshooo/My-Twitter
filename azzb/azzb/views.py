from django.conf import settings
from django.shortcuts import render
from django.views.generic.detail import DetailView

from .models import Profile
from post.models import Post
#from .serializers import PostSerializer

def index(request):
	latest_posts = Post.objects.order_by("-created_at")[:10].select_related("author")
	context = {"latest_posts": latest_posts}
	return render(request, "azzb/azzb_indexPage.html", context)

#class PostListAPIView(APIView):
#	def get(self, request, id):
#		posts = Post.objects.filter(author=id)
#		serializer = PostSerializer(posts, many=True)
#		return response({"data": serializer.data}, status=status.HTTP_200_OK)
