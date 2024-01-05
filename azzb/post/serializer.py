from rest_framework import serializers

from post.models import Post

class PostSerializer(serializers.ModelSerializer):
	
	def create(self, validated_data):
		"""
		Создаёт и возвращает экземпляр Post.
		"""
		try:
			instance = Post.objects.create(**validated_data)
		except TypeError:
			raise TypeError("error(")
		return instance
	class Meta:
		model = Post
		fields = "__all__"