from django.db.models import Count
from django.shortcuts import render

from post.models import Post


def _feed_posts():
	return Post.objects.select_related("author__user").prefetch_related("images")


def _render_feed(request, feed, posts, **extra):
	context = {"feed": feed, "posts": posts, **extra}
	return render(request, "azzb/feed.html", context)


def index(request):
	latest_posts = _feed_posts().order_by("-created_at")[:10]
	# Свой новый пост из composer логично показать сверху именно «Свежего».
	return _render_feed(request, "latest", latest_posts, prepend=True)


def follows_updates(request):
	follows = request.user.profile.follows.all()
	follows_posts = _feed_posts().filter(author__in=follows)
	return _render_feed(request, "following", follows_posts)


def hot_news(request):
	hot_posts = _feed_posts().annotate(num_likes=Count('likes')).order_by('-num_likes', '-created_at')
	return _render_feed(request, "hot", hot_posts)
