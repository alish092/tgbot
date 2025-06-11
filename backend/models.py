from tortoise import models, fields
from datetime import datetime
from pydantic import BaseModel, conint


class Log(models.Model):
    id = fields.BigIntField(pk=True)
    user_id = fields.BigIntField()
    username = fields.CharField(max_length=255)
    question = fields.CharField(max_length=1024)
    answer = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)  # 👈 Добавь это

class Complaint(models.Model):
    id = fields.BigIntField(pk=True)
    log = fields.ForeignKeyField("models.Log", related_name="complaints", unique=True)
    complaint = fields.TextField()
    status = fields.CharField(max_length=50, null=True)

class Role(models.Model):
    user_id = fields.BigIntField(pk=True)
    username = fields.CharField(max_length=100, null=True)  # добавляем поле
    role = fields.CharField(max_length=100)

class LogInput(BaseModel):
    user_id: conint(ge=1)  # или просто user_id: int, но это не ограничит по int64
    username: str
    question: str
    answer: str

class Override(models.Model):
    id = fields.IntField(pk=True)
    question = fields.CharField(max_length=1024, unique=True)
    answer = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True, null=True)  # Добавляем с null=True

class Synonym(models.Model):
    id = fields.IntField(pk=True)
    keyword = fields.CharField(max_length=100)
    synonym = fields.CharField(max_length=100)

    class Meta:
        table = "synonym"
        schema = "public"

class Priority(models.Model):
    id = fields.IntField(pk=True)
    keyword = fields.CharField(max_length=100)
    document_name = fields.CharField(max_length=255)
class QueryStats(models.Model):
    id = fields.IntField(pk=True)
    question = fields.CharField(max_length=1024)
    count = fields.IntField(default=1)
    success_rate = fields.FloatField(default=0.0)  # Процент успешных ответов (без жалоб)
    first_asked = fields.DatetimeField(auto_now_add=True)
    last_asked = fields.DatetimeField(auto_now=True)

