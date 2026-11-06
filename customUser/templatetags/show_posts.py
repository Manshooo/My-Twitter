from django import template

from post.models import reply_counts

register = template.Library()

@register.inclusion_tag(filename='post/post.html', name="show_posts", takes_context=True)
def show_posts(context, variant=""):
	"""Карточка поста. variant: "" — в ленте, "main" — главный пост на своей странице,
	"parent" — пост выше по ветке (с линией к следующему)."""
	post = context["post"]
	request = context["request"]
	# Лента приходит из Post.objects.for_feed(): там число лайков и «мой ли лайк» уже посчитаны
	# в том же запросе. Запасной путь — для поста, загруженного без аннотаций.
	liked = getattr(post, "is_liked", None)
	if liked is None:
		liked = request.user.is_authenticated and post.likes.filter(pk=request.user.profile.pk).exists()
	likes_total = getattr(post, "likes_n", None)
	if likes_total is None:
		likes_total = post.likes.count()
	replies_total = getattr(post, "replies_n", None)
	if replies_total is None:
		replies_total = reply_counts([post], request.user)[post.pk]
	return {
		"post": post, "liked": liked, "likes_total": likes_total, "replies_total": replies_total,
		"variant": variant, "request": request, "user": request.user,
	}
