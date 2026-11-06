from django.contrib import admin

from . import services
from .models import Ban, Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
	list_display = ('created_at', 'reason', 'status', 'profile', 'post', 'reporter', 'resolved_by')
	list_filter = ('status', 'reason')
	search_fields = ('profile__user__username', 'reporter__user__username', 'comment')
	raw_id_fields = ('reporter', 'post', 'profile', 'resolved_by')
	date_hierarchy = 'created_at'


@admin.register(Ban)
class BanAdmin(admin.ModelAdmin):
	"""История банов только для просмотра: банят и снимают бан через очередь модерации и профиль,
	чтобы CustomUser.banned_until всегда совпадал с историей."""
	list_display = ('created_at', 'user', 'until', 'reason', 'created_by', 'lifted_at')
	search_fields = ('user__username', 'reason')
	readonly_fields = [field.name for field in Ban._meta.fields]
	actions = ['lift']

	def has_add_permission(self, request):
		return False

	@admin.action(description='Снять бан')
	def lift(self, request, queryset):
		for user in {ban.user for ban in queryset}:
			services.unban_user(request.user, user)
