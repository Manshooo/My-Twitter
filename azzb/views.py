from django.shortcuts import render

from post.models import Post
from post.pagination import PAGE_TEMPLATE, cursor_page, is_load_more, number_page, page_url

FEED_TEMPLATE = "azzb/feed.html"


def render_posts(request, template, context, posts, next_params):
	context.update({
		"posts": posts,
		"next_url": page_url(request, **next_params) if next_params else None,
	})
	return render(request, PAGE_TEMPLATE if is_load_more(request) else template, context)


def index(request):
	posts, cursor = cursor_page(Post.objects.for_feed(request.user), request.GET.get("cursor"))
	# Свой новый пост из composer логично показать сверху именно «Свежего».
	context = {"feed": "latest", "prepend": True}
	return render_posts(request, FEED_TEMPLATE, context, posts, cursor and {"cursor": cursor})


def follows_updates(request):
	follows = request.user.profile.follows.all()
	queryset = Post.objects.for_feed(request.user).filter(author__in=follows)
	posts, cursor = cursor_page(queryset, request.GET.get("cursor"))
	return render_posts(request, FEED_TEMPLATE, {"feed": "following"}, posts, cursor and {"cursor": cursor})


def hot_news(request):
	queryset = Post.objects.for_feed(request.user).order_by("-likes_n", "-created_at", "-id")
	posts, next_page = number_page(queryset, request.GET.get("page"))
	return render_posts(request, FEED_TEMPLATE, {"feed": "hot"}, posts, next_page and {"page": next_page})
