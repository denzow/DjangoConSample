from django.db import models


class Book(models.Model):
    name = models.CharField(max_length=200)


class Author(models.Model):
    name = models.CharField(max_length=200)
