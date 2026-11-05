from django import template

register = template.Library()

@register.inclusion_tag(filename='post/post.html', name="show_posts", takes_context=True)
def show_posts(context):
	post = context["post"]
	request = context["request"]
	liked = False
	if request.user.is_authenticated:
		# exists() вместо загрузки всех лайков поста ради одной проверки.
		liked = post.likes.filter(pk=request.user.profile.pk).exists()
	return {"post": post, "liked": liked, "request": request, "user": request.user}
