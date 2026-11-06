from django import template

register = template.Library()

@register.inclusion_tag(filename='post/post.html', name="show_posts", takes_context=True)
def show_posts(context, variant=""):
	"""Карточка поста. variant: "" — в ленте, "main" — главный пост на своей странице,
	"parent" — пост выше по ветке (с линией к следующему).
	Пост из ветки, который пользователь не видит (available=False, см. Post.objects.in_thread),
	выводится заглушкой без автора и текста — gone говорит, почему."""
	post = context["post"]
	request = context["request"]
	if getattr(post, "available", True) is False:
		gone = "deleted" if post.deleted_at else "hidden" if post.hidden_at else "unavailable"
		return {"post": post, "gone": gone, "variant": variant, "request": request, "user": request.user}
	# Лента приходит из Post.objects.for_feed(): там число лайков и «мой ли лайк» уже посчитаны
	# в том же запросе. Запасной путь — для поста, загруженного без аннотаций.
	liked = getattr(post, "is_liked", None)
	if liked is None:
		liked = request.user.is_authenticated and post.likes.filter(pk=request.user.profile.pk).exists()
	likes_total = getattr(post, "likes_n", None)
	if likes_total is None:
		likes_total = post.likes.count()
	replies_total = post.replies_count
	return {
		"post": post, "liked": liked, "likes_total": likes_total, "replies_total": replies_total,
		"variant": variant, "request": request, "user": request.user,
	}
