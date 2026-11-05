from django import template

register = template.Library()

@register.inclusion_tag(filename='post/post.html', name="show_posts", takes_context=True)
def show_posts(context):
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
	return {"post": post, "liked": liked, "likes_total": likes_total, "request": request, "user": request.user}
