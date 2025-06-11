from fastapi import FastAPI, Request, HTTPException, Query, Path, Depends, Response
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from tortoise.contrib.fastapi import register_tortoise
from tortoise.expressions import Q
from tortoise.functions import Count
from tortoise.exceptions import DoesNotExist
from tortoise import Tortoise
from datetime import datetime, timedelta
from typing import Optional
import csv
import io
import json
from pydantic import BaseModel
from models import LogInput
from models import Log, Complaint, Role, Override, Synonym, Priority
from datetime import datetime, timedelta, timezone
# from sentence_transformers import SentenceTransformer
# from sklearn.cluster import DBSCAN
# import numpy as np
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Конкретный origin вашего фронтенда
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
class ManualResponseInput(BaseModel):
    manual_response: str
@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/logs")
async def get_logs(
        page: int = Query(1, description="Номер страницы"),
        limit: int = Query(20, description="Количество записей на странице"),
        search: Optional[str] = Query(None, description="Общий поиск по вопросу или ответу"),
        username: Optional[str] = Query(None, description="Фильтр по пользователю"),
        question: Optional[str] = Query(None, description="Фильтр по вопросу"),
        answer: Optional[str] = Query(None, description="Фильтр по ответу")

):
    query = Log.all()

    # Общий поиск (как было раньше)
    if search:
        query = query.filter(Q(question__icontains=search) | Q(answer__icontains=search))

    # Отдельные фильтры
    if username:
        query = query.filter(username__icontains=username)

    if question:
        query = query.filter(question__icontains=question)

    if answer:
        query = query.filter(answer__icontains=answer)

    total = await query.count()
    offset = (page - 1) * limit
    logs = await query.order_by('-id').offset(offset).limit(limit).values(
        "id", "user_id", "username", "question", "answer", "created_at"
    )

    return {
        "items": logs,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }


@app.post("/logs")
async def add_log(data: LogInput):
    try:
        logger.debug(f"Начало логирования: {data.question[:20]}...")

        log = await Log.create(
            user_id=data.user_id,
            username=data.username,
            question=data.question,
            answer=data.answer,
        # Убираем created_at полностью
        )

        logger.debug(f"✅ Log записан: {log.id}")
        return {"id": log.id}
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"❌ ПОЛНЫЙ СТЕК-ТРЕЙС ОШИБКИ:\n{error_traceback}")
        return {"error": str(e)}


@app.get("/logs/export")
async def export_logs(
    format: str = Query("csv", description="Формат экспорта (csv или json)"),
    search: Optional[str] = Query(None, description="Поиск по вопросу или ответу")
):
    query = Log.all()
    if search:
        if search:
            query = query.filter(
                Q(question__icontains=search) |
                Q(answer__icontains=search) |
                Q(username__icontains=search)
            )
    logs = await query.order_by('-id')
    logs_data = [
        {
            "id": log.id,
            "user_id": log.user_id,
            "username": log.username,
            "question": log.question,
            "answer": log.answer,
            "created_at": log.created_at.isoformat() if hasattr(log, 'created_at') else None
        }
        for log in logs
    ]

    filename = f"logs_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    if not logs_data:
        return Response(content="", media_type="text/csv")

    if format == "json":
        content = json.dumps(logs_data, ensure_ascii=False, indent=2)
        filename = f"{filename}.json"
        response = Response(content=content, media_type="application/json")
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        return response
    else:
        output = io.StringIO()
        headers = logs_data[0].keys()
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(logs_data)
        filename = f"{filename}.csv"
        response = Response(content=output.getvalue(), media_type="text/csv")
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        return response


@app.post("/complaints")
async def add_complaint(log_id: int, complaint: str):
    try:
        log = await Log.get_or_none(id=log_id)
        if not log:
            raise HTTPException(status_code=404, detail=f"Log with id {log_id} not found")

        # Вот здесь изменения
        try:
            # Пробуем создать жалобу с минимальным набором полей
            new_complaint = await Complaint.create(
                log=log,
                complaint=complaint,
                status="PENDING"
            )
        except Exception as create_error:
            # Если ошибка связана с полями, пробуем создать жалобу без created_at
            print(f"Ошибка при создании жалобы: {str(create_error)}")
            # Выводим все доступные поля модели
            print(f"Доступные поля модели: {Complaint._meta.fields}")

            # Создаем жалобу вручную через SQL
            from tortoise.expressions import RawSQL
            await Complaint.raw(
                "INSERT INTO complaint (log_id, complaint, status) VALUES (?, ?, ?)",
                [log.id, complaint, "PENDING"]
            )

            # Получаем созданную жалобу
            new_complaint = await Complaint.filter(log=log).order_by("-id").first()

        # Добавляем информацию о жалобе для логирования
        log_info = {
            "id": new_complaint.id if new_complaint else None,
            "log_id": log_id,
            "complaint": complaint,
            "username": log.username,
            "question": log.question,
            "answer": log.answer
        }

        print(f"✅ Создана жалоба: {log_info}")
        return {"id": new_complaint.id if new_complaint else None, "details": log_info}
    except Exception as e:
        print(f"❌ Ошибка при создании жалобы: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")


@app.get("/complaints")
async def get_complaints():
    try:
        print("Получение жалоб...")
        complaints = await Complaint.all().prefetch_related("log")
        print(f"Найдено жалоб: {len(complaints)}")
        result = []

        for c in complaints:
            try:
                complaint_data = {
                    "id": c.id,
                    "question": c.log.question if c.log and hasattr(c.log, "question") else "",
                    "username": c.log.username if c.log and hasattr(c.log, "username") else "",
                    "answer": c.log.answer if c.log and hasattr(c.log, "answer") else "",
                    "user_id": c.log.user_id if c.log and hasattr(c.log, "user_id") else None,
                    "complaint": c.complaint,
                    "status": c.status,
                    #"created_at": c.created_at.isoformat() if hasattr(c, "created_at") else "",
                    #"resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
                }
                result.append(complaint_data)
            except Exception as e:
                print(f"Ошибка при обработке жалобы {c.id}: {str(e)}")

        print(f"Возвращаю {len(result)} жалоб")
        return result
    except Exception as e:
        print(f"Ошибка в эндпоинте /complaints: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


@app.get("/complaints/{complaint_id}")
async def get_complaint_detail(complaint_id: int):
    try:
        complaint = await Complaint.filter(id=complaint_id).prefetch_related("log").first()
        if not complaint:
            raise HTTPException(status_code=404, detail="Жалоба не найдена")

        return {
            "id": complaint.id,
            "question": complaint.log.question if complaint.log else "",
            "username": complaint.log.username if complaint.log else "",
            "answer": complaint.log.answer if complaint.log else "",
            "user_id": complaint.log.user_id if complaint.log else None,
            "complaint": complaint.complaint,
            "status": complaint.status,
            #"created_at": complaint.created_at.isoformat() if hasattr(complaint, "created_at") else "",
            #"resolved_at": complaint.resolved_at.isoformat() if complaint.resolved_at else None,
        }
    except Exception as e:
        print(f"Ошибка при получении деталей жалобы {complaint_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")


@app.post("/complaints/{complaint_id}/override")
async def override_complaint(complaint_id: int, data: ManualResponseInput):
    manual_response = data.manual_response
    try:
        if not manual_response or not manual_response.strip():
            raise HTTPException(status_code=400, detail="Текст ответа не может быть пустым")

        complaint = await Complaint.filter(id=complaint_id).prefetch_related("log").first()
        if not complaint:
            raise HTTPException(status_code=404, detail=f"Жалоба с ID {complaint_id} не найдена")

        log = complaint.log
        if not log:
            raise HTTPException(status_code=404, detail=f"Связанный лог не найден для жалобы {complaint_id}")

        old_answer = log.answer

        # Обновляем ответ в логе
        log.answer = manual_response
        log.is_manually_overridden = True
        await log.save()

        # Обновляем статус жалобы
        complaint.status = "RESOLVED"
        await complaint.save()

        # 🔥 Добавляем ручной ответ в overrides, если его ещё нет
        exists = await Override.filter(question=log.question).first()
        if not exists:
            await Override.create(
                question=log.question,
                answer=manual_response
            )
            print(f"📝 Добавлен новый ручной ответ в Override")

        # Логирование
        print(f"✅ Отправлен ручной ответ для жалобы {complaint_id}")
        print(f"   Пользователь: {log.username} (ID: {log.user_id})")
        print(f"   Старый ответ: {old_answer}")
        print(f"   Новый ответ: {manual_response}")

        return {
            "success": True,
            "user_id": log.user_id,
            "complaint_id": complaint_id,
            "manual_response": manual_response
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"❌ Ошибка при обработке ручного ответа для жалобы {complaint_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")
class RoleInput(BaseModel):
    user_id: int
    username: str
    role: str
@app.get("/roles")
async def get_roles():
    return await Role.all().order_by("user_id").values("user_id", "username", "role")
@app.post("/roles")
async def set_role(
    user_id: int = Query(...),
    username: str = Query(...),
    role: str = Query(...)
):
    existing = await Role.filter(user_id=user_id).first()
    if existing:
        existing.role = role
        await existing.save()
        return existing
    return await Role.create(user_id=user_id, username=username, role=role)

@app.delete("/roles/{user_id}")
async def delete_role(user_id: int):
    await Role.filter(user_id=user_id).delete()
    return {"status": "deleted"}
@app.delete("/overrides/{override_id}")
async def delete_override(override_id: int):
    deleted = await Override.filter(id=override_id).delete()
    if deleted:
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Override not found")
@app.get("/overrides")
async def get_overrides():
    return await Override.all().order_by("-id")

@app.post("/overrides")
async def add_override(question: str, answer: str):
    print("🟡 Поступил POST /overrides")
    print("   Вопрос:", question)
    print("   Ответ:", answer)

    existing = await Override.filter(question=question).first()
    if existing:
        existing.answer = answer
        await existing.save()
        print("🔄 Обновлён существующий override")
        return {"id": existing.id,
    "question": existing.question,
    "answer": existing.answer}

    try:
        new = await Override.create(question=question, answer=answer)
        print("✅ Создан новый override с ID:", new.id)
        return { "id": new.id,
    "question": new.question,
    "answer": new.answer}
    except Exception as e:
        print("❌ Ошибка при создании override:", str(e))
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка при добавлении override: {str(e)}")


@app.put("/overrides/{id}")
async def update_override(
    id: int = Path(..., description="ID ручного ответа"),
    question: str = "",
    answer: str = ""
):
    override = await Override.get_or_none(id=id)
    if not override:
        raise HTTPException(status_code=404, detail="Override not found")
    override.question = question
    override.answer = answer
    await override.save()
    return {"status": "ok"}

@app.get("/stats")
async def get_stats():
    now = datetime.now(timezone.utc)
    today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    # Общие подсчёты
    logs_count = await Log.all().count()
    overrides_count = await Override.all().count()
    unique_log_ids = await Complaint.all().values_list("log_id", flat=True)
    complaints_count = len(set(unique_log_ids))

    # Самый активный пользователь
    top_user_obj = await Log.annotate(count=Count("id")).group_by("username").order_by("-count").first()

    stats_today = await Log.filter(created_at__gte=today).count()
    stats_week = await Log.filter(created_at__gte=today - timedelta(days=7)).count()
    stats_month = await Log.filter(created_at__gte=today - timedelta(days=30)).count()

    # Получаем все вопросы и их частоты
    raw_questions = await Log.all().values("question")
    question_freq = {}
    for row in raw_questions:
        q = row["question"].strip().lower()
        question_freq[q] = question_freq.get(q, 0) + 1

    # Эмбеддим и кластеризуем
    texts = list(question_freq.keys())
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.cluster import DBSCAN
        import numpy as np

        if texts:
            model = SentenceTransformer("all-MiniLM-L6-v2")
            embeddings = model.encode(texts)
            clustering = DBSCAN(eps=0.45, min_samples=1, metric="cosine").fit(embeddings)

            clusters = {}
            for i, label in enumerate(clustering.labels_):
                clusters.setdefault(label, []).append((texts[i], question_freq[texts[i]]))

            clustered_questions = []
            for group in clusters.values():
                group.sort(key=lambda x: x[1], reverse=True)
                main_text, total = group[0][0], sum(x[1] for x in group)
                clustered_questions.append({"name": main_text, "запросы": total})

            clustered_questions.sort(key=lambda x: -x["запросы"])
            clustered_questions = clustered_questions[:10]
        else:
            clustered_questions = []
    except ImportError:
        print("⚠️ sentence-transformers или sklearn не установлены — fallback на частотный список")
        clustered_questions = [
            {"name": q, "запросы": c} for q, c in sorted(question_freq.items(), key=lambda x: -x[1])[:10]
        ]

    return {
        "total_logs": logs_count,
        "total_complaints": complaints_count,
        "total_overrides": overrides_count,
        "top_user": top_user_obj.username if top_user_obj else None,
        "top_count": top_user_obj.count if top_user_obj else None,
        "stats_today": stats_today,
        "stats_week": stats_week,
        "stats_month": stats_month,
        "top_questions": clustered_questions,
        "complaints_ratio": round(complaints_count / logs_count * 100, 2) if logs_count > 0 else 0,
    }


@app.post("/synonyms")
async def add_synonym(keyword: str, synonym: str):
    logger.info(f"🔄 Попытка добавить синоним: {keyword} → {synonym}")

    # Начинаем транзакцию явно
    conn = Tortoise.get_connection("default")
    await conn.execute_query("BEGIN;")

    try:
        existing = await Synonym.filter(keyword=keyword, synonym=synonym).first()
        if existing:
            await conn.execute_query("COMMIT;")
            return existing

        new_synonym = await Synonym.create(keyword=keyword, synonym=synonym)
        await conn.execute_query("COMMIT;")
        logger.info(f"✅ Синоним добавлен в базу: {new_synonym.keyword} → {new_synonym.synonym}")
        return new_synonym
    except Exception as e:
        # В случае ошибки откатываем транзакцию
        await conn.execute_query("ROLLBACK;")
        logger.error(f"❌ Ошибка при добавлении синонима: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при добавлении синонима: {str(e)}")

@app.get("/synonyms_from_db")
async def get_synonyms():
    # Добавьте логирование для отладки
    synonyms = await Synonym.all()
    logger.debug(f"Получено {len(synonyms)} синонимов из базы")
    for s in synonyms:
        logger.debug(f"  - {s.keyword} → {s.synonym}")
    return await Synonym.all()

@app.post("/priorities")
async def add_priority(keyword: str, document_name: str):
    existing = await Priority.filter(keyword=keyword).first()
    if existing:
        existing.document_name = document_name
        await existing.save()
        return existing
    return await Priority.create(keyword=keyword, document_name=document_name)

@app.get("/priorities")
async def get_priorities():
    return await Priority.all()

@app.delete("/priorities/{priority_id}")
async def delete_priority(priority_id: int):
    deleted = await Priority.filter(id=priority_id).delete()
    if deleted:
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Priority not found")

@app.get("/health")
async def health_check():
    try:
        log_count = await Log.all().count()
        return {"status": "healthy", "log_count": log_count}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

register_tortoise(
    app,
    db_url="postgres://bot:secret@db:5432/bot_db",
    modules={"models": ["models"]},
    generate_schemas=True,
    add_exception_handlers=True,
)
