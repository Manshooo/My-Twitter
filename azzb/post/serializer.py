from rest_framework import serializers

from post.models import Post

class PostSerializer(serializers.ModelSerializer):
	likes_count = serializers.IntegerField(read_only=True)

	class Meta:
		model = Post
		# Клиент может задать только текст. Автор проставляется во view из request.user;
		# раньше через "__all__" можно было передать произвольный список лайков.
		fields = ['id', 'text', 'author', 'created_at', 'updated', 'likes_count']
		read_only_fields = ['id', 'author', 'created_at', 'updated', 'likes_count']
