from django.contrib import admin

from .models import Image, Post, PostRevision


class ImageInline(admin.TabularInline):
	model = Image
	extra = 0
	fields = ('file', 'alt', 'position', 'width', 'height')
	readonly_fields = ('width', 'height')


class RevisionInline(admin.TabularInline):
	model = PostRevision
	extra = 0
	fields = ('valid_from', 'replaced_at', 'text')
	readonly_fields = fields
	can_delete = False

	def has_add_permission(self, request, obj=None):
		return False


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
	list_display = ('created_at', 'author', 'short_text', 'is_reply', 'edited_at')
	list_select_related = ('author',)
	search_fields = ('text', 'author__user__username')
	date_hierarchy = 'created_at'
	readonly_fields = ('id', 'created_at', 'updated', 'edited_at')
	raw_id_fields = ('author', 'reply_to')
	exclude = ('likes',)
	inlines = [ImageInline, RevisionInline]

	@admin.display(description='Текст')
	def short_text(self, post):
		return post.text[:80]
