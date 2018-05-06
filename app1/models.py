from django.db import models


class Book(models.Model):
    name = models.CharField(max_length=200)
    author = models.ForeignKey('Author', on_delete=models.CASCADE, default=None, null=True)


class Author(models.Model):
    name = models.CharField(max_length=200)
