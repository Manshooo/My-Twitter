from django.contrib import admin

from .models import Image, Post


class ImageInline(admin.TabularInline):
	model = Image
	extra = 0
	fields = ('file', 'alt', 'position', 'width', 'height')
	readonly_fields = ('width', 'height')


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
	list_display = ('created_at', 'author', 'short_text')
	list_select_related = ('author',)
	search_fields = ('text', 'author__user__username')
	date_hierarchy = 'created_at'
	raw_id_fields = ('author',)
	readonly_fields = ('id', 'created_at', 'updated')
	exclude = ('likes',)
	inlines = [ImageInline]

	@admin.display(description='Текст')
	def short_text(self, post):
		return post.text[:80]
