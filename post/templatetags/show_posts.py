from django import template

from post.models import Post

register = template.Library()

# Аннотации из Post.objects.for_feed(), которые у репоста посчитаны для исходного поста (по shown_id).
SHOWN_ANNOTATIONS = ('likes_n', 'is_liked', 'is_reposted', 'is_bookmarked', 'quote_available')


@register.inclusion_tag(filename='post/post.html', name="show_posts", takes_context=True)
def show_posts(context, variant=""):
	"""Карточка поста. variant: "" — в ленте, "main" — главный пост на своей странице,
	"parent" — пост выше по ветке (с линией к следующему), "chain" — сообщение разговора
	под ответом (post/_conversation.html).
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


@register.inclusion_tag(filename='post/_poll.html', takes_context=True)
def poll_block(context, post):
	"""Опрос в карточке. Числа отдаём в HTML только тем, кому положено их видеть: автору,
	проголосовавшим и всем после окончания, — иначе результаты подсмотрели бы в коде страницы."""
	poll = post.poll
	user = context["request"].user
	mine = getattr(poll, "mine", None)
	if mine is None:
		mine = list(poll.votes.filter(profile_id=user.profile.pk)) if user.is_authenticated else []
	my_option = mine[0].option_id if mine else None
	options = list(poll.options.all())
	for option in options:
		if not hasattr(option, "votes_n"):
			option.votes_n = option.votes.count()
	total = sum(option.votes_n for option in options)
	for option in options:
		option.percent = round(100 * option.votes_n / total) if total else 0
	is_author = user.is_authenticated and post.author_id == user.pk
	return {
		"post": post, "poll": poll, "options": options, "total": total, "my_option": my_option,
		"show_results": is_author or my_option is not None or not poll.is_open,
		"can_vote": user.is_authenticated and not is_author and my_option is None and poll.is_open,
		"request": context["request"], "user": user,
	}
