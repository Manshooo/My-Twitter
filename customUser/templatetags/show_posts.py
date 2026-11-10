from django import template

from post.models import Post

register = template.Library()

# Аннотации из Post.objects.for_feed(), которые у репоста посчитаны для исходного поста (по shown_id).
SHOWN_ANNOTATIONS = ('likes_n', 'is_liked', 'is_reposted', 'is_bookmarked', 'quote_available')


@register.inclusion_tag(filename='post/post.html', name="show_posts", takes_context=True)
def show_posts(context, variant=""):
	"""Карточка поста. variant: "" — в ленте, "main" — главный пост на своей странице,
	"parent" — пост выше по ветке (с линией к следующему).
	Пост из ветки, который пользователь не видит (available=False, см. Post.objects.in_thread),
	выводится заглушкой без автора и текста — gone говорит, почему.
	Репост выводится карточкой исходного поста с пометкой «X сделал(а) репост» (D4)."""
	row = context["post"]
	request = context["request"]
	if getattr(row, "available", True) is False:
		gone = "deleted" if row.deleted_at else "hidden" if row.hidden_at else "unavailable"
		return {"post": row, "gone": gone, "variant": variant, "request": request, "user": request.user}
	post, reposted_by = row, None
	if row.is_repost and row.repost_of is not None:
		post, reposted_by = row.repost_of, row.author
		for name in SHOWN_ANNOTATIONS:
			if hasattr(row, name):
				setattr(post, name, getattr(row, name))
	# Лента приходит из Post.objects.for_feed(): там число лайков и «мой ли лайк» уже посчитаны
	# в том же запросе. Запасной путь — для поста, загруженного без аннотаций.
	liked = getattr(post, "is_liked", None)
	if liked is None:
		liked = request.user.is_authenticated and post.likes.filter(pk=request.user.profile.pk).exists()
	likes_total = getattr(post, "likes_n", None)
	if likes_total is None:
		likes_total = post.likes.count()
	quote = post.quote_of if post.quote_of_id else None
	quote_available = getattr(post, "quote_available", None)
	if quote is not None and quote_available is None:
		quote_available = Post.objects.visible_to(request.user).filter(pk=quote.pk).exists()
	return {
		"post": post, "liked": liked, "likes_total": likes_total, "replies_total": post.replies_count,
		"reposted": getattr(post, "is_reposted", False), "reposts_total": post.reposts_count,
		"bookmarked": getattr(post, "is_bookmarked", False),
		"reposted_by": reposted_by, "repost_row": row if reposted_by else None,
		# Одна и та же карточка может стоять на странице дважды (пост и его репост): id меню — по строке.
		"key": row.pk,
		"quote": quote, "quote_available": quote is not None and quote_available,
		"variant": variant, "request": request, "user": request.user,
	}
