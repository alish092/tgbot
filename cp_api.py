from flask import Flask, send_from_directory, request, abort
import os

app = Flask(__name__)

# Путь к папке с КП-файлами на Windows
CP_FOLDER =  os.getenv("CP_FOLDER")

@app.route("/get_cp")
def get_cp():
    cp_code = request.args.get("code")
    if not cp_code:
        return abort(400, "Не указан код КП")

    for ext in [".pdf", ".xlsx", ".xls"]:
        filename = f"{cp_code}{ext}"
        file_path = os.path.join(CP_FOLDER, filename)
        if os.path.exists(file_path):
            return send_from_directory(CP_FOLDER, filename, as_attachment=True)

    return abort(404, f"КП {cp_code} не найден")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
