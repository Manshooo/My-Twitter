from django import template

from post.models import Post

register = template.Library()

@register.inclusion_tag(filename='post/post.html', name="show_posts", takes_context=True)
def show_posts(context):
	post = context["post"]
	request = context["request"]
	context["liked"] = False
	if post.likes.filter(pk=request.user.profile.id).exists():
		context["liked"] = True
	return context