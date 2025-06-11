from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import os

app = FastAPI()

# Путь к папке с КП на сетевом ресурсе
CP_FOLDER = r"\\srv-2\обмен\Отдел продаж\Наличие 2023_производство 2024"

@app.get("/get_cp")
def get_cp(code: str):
    filename = f"{code.upper()}.pdf"
    filepath = os.path.join(CP_FOLDER, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="КП не найдено")

    return FileResponse(filepath, media_type="application/pdf", filename=filename)