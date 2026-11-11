from django import template
from django.utils.safestring import mark_safe

from azzb import seo

register = template.Library()


class CaptureNode(template.Node):
	# Блоки внутри capture переопределяются в дочерних шаблонах: ExtendsNode ищет их по child_nodelists.
	child_nodelists = ('nodelist',)

	def __init__(self, nodelist, name):
		self.nodelist = nodelist
		self.name = name

	def render(self, context):
		# Текст уже отрисован с автоэкранированием — повторно экранировать нельзя.
		context[self.name] = mark_safe(self.nodelist.render(context).strip())
		return ''


@register.tag
def capture(parser, token):
	"""{% capture as name %}...{% endcapture %}: отрисовать кусок один раз и вывести его в нескольких местах
	(<title> и og:title из одного блока title)."""
	bits = token.split_contents()
	if len(bits) != 3 or bits[1] != 'as':
		raise template.TemplateSyntaxError("Формат: {% capture as имя %}")
	nodelist = parser.parse(('endcapture',))
	parser.delete_first_token()
	return CaptureNode(nodelist, bits[2])


@register.simple_tag(takes_context=True)
def absolute(context, url):
	"""Полный адрес для og:image и canonical. Адрес из S3 уже полный — он вернётся как есть."""
	return context['request'].build_absolute_uri(url)


@register.simple_tag(takes_context=True)
def canonical(context):
	return context['request'].build_absolute_uri(context['request'].path)


@register.simple_tag(takes_context=True)
def jsonld_post(context, post):
	return seo.script(seo.post(context['request'], post))


@register.simple_tag(takes_context=True)
def jsonld_profile(context, profile):
	return seo.script(seo.profile_page(context['request'], profile))


@register.simple_tag(takes_context=True)
def jsonld_website(context):
	return seo.script(seo.website(context['request']))
