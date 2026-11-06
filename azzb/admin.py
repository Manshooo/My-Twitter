from django.contrib import admin

from customUser.models import Block, CustomUser, FollowThrough, Mute, Profile

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
	list_display = ["username", "email", "first_name", "last_name", "last_visit", "last_login", "date_joined"]
	fields = ["username", "password", "first_name", "last_name", "email", "last_login", "date_joined", "banned_until", "ban_reason"]
	# Бан ставится через очередь модерации (история в «Банах»), здесь — только посмотреть.
	readonly_fields = ["banned_until", "ban_reason"]
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
