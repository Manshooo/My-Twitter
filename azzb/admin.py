from django.contrib import admin

from accounts.models import Block, CustomUser, FollowThrough, Mute, Profile

from .models import ActivityRecord


class FollowThroughInlineAdmin(admin.TabularInline):
	model = FollowThrough
	extra = 1
	fk_name = "follower"
class UserProfileAdmin(admin.ModelAdmin):
	model = Profile
	inlines = [FollowThroughInlineAdmin]
	list_display = ["username", "user", "is_verified", "likes_public"]
	list_editable = ["is_verified"]
	list_filter = ["is_verified"]
	search_fields = ["username", "user__username"]

class UserAdmin(admin.ModelAdmin):
	model = CustomUser
	list_display = ["username", "email", "first_name", "last_name", "last_visit", "last_login", "date_joined", "deleted_at"]
	list_filter = ["deleted_at", "erased_at"]
	fields = [
		"username", "password", "first_name", "last_name", "email", "last_login", "date_joined",
		"banned_until", "ban_reason", "deleted_at", "erased_at",
	]
	# Бан ставится через очередь модерации (история в «Банах»), здесь — только посмотреть.
	# Удаление и стирание — кнопкой в настройках аккаунта и командой purge_expired.
	readonly_fields = ["banned_until", "ban_reason", "deleted_at", "erased_at"]
	search_fields = ["username", "email"]


# Группы нужны: участники группы «Модераторы» получают доступ к /moderation/ (E4).
admin.site.register(CustomUser, UserAdmin)
admin.site.register(Profile, UserProfileAdmin)


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
	list_display = ("blocker", "blocked", "created_at")
	raw_id_fields = ("blocker", "blocked")


@admin.register(Mute)
class MuteAdmin(admin.ModelAdmin):
	list_display = ("muter", "muted", "created_at")
	raw_id_fields = ("muter", "muted")


@admin.register(ActivityRecord)
class ActivityRecordAdmin(admin.ModelAdmin):
	"""Журнал действий: только смотреть — для ответа на законный запрос госорганов."""
	list_display = ("created_at", "username", "action", "ip", "post_id")
	list_filter = ("action",)
	search_fields = ("username", "email", "ip", "post_id")
	date_hierarchy = "created_at"
	readonly_fields = [field.name for field in ActivityRecord._meta.fields]

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False
