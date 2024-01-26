from django import template

from post.models import Post

register = template.Library()

@register.inclusion_tag(filename='post/post.html', name="show_posts", takes_context=True)
def show_posts(context):

	post = context["post"]
	request = context["request"]

	context["liked"] = False
	if request.user.is_authenticated:
		if request.user.profile in post.get_likes().all():
			context["liked"] = True
		return context
	else:
		return context
