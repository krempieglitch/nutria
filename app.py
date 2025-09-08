from flask import Flask, request, jsonify
import os, requests, json
from google.oauth2.service_account import Credentials
import gspread

app = Flask(__name__)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

def openai_chat(messages, model="gpt-4o-mini", response_format=None):
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages}
    if response_format:
        payload["response_format"] = response_format
    r = requests.post(OPENAI_CHAT_URL, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def coerce_json(s):
    try:
        return json.loads(s)
    except:
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end != -1 and end > start:
            try: return json.loads(s[start:end+1])
            except: pass
        return {"raw": s}

@app.route("/", methods=["GET"])
def root():
    return jsonify({"ok": True, "service": "nutrition-bot"})

@app.route("/count-calories", methods=["POST"])
def count_calories():
    data = request.get_json(force=True)
    text = data.get("prompt", "")
    sys = ("Ты нутрициолог. Пользователь перечисляет продукты. "
           "Разбери, оцени массу, калории и макросы. "
           "Ответь JSON: {'items':[{'name':str,'amount_g':number,'kcal':number,'protein_g':number,'fat_g':number,'carb_g':number}],"
           "'total':{'kcal':number,'protein_g':number,'fat_g':number,'carb_g':number}}")
    result = coerce_json(openai_chat([{"role":"system","content":sys},{"role":"user","content":text}]))
    return jsonify(result)

@app.route("/diet", methods=["POST"])
def diet():
    profile = request.get_json(force=True)
    sys = ("Ты нутрициолог. Составь план питания по профилю пользователя "
           "и верни JSON: {'calorie_target':number,'meals':[{'title':str,'items':[{'name':str,'amount_g':number,'kcal':number}]}]}")
    result = coerce_json(openai_chat([{"role":"system","content":sys},{"role":"user","content":json.dumps(profile, ensure_ascii=False)}]))
    return jsonify(result)

@app.route("/analyze-photo", methods=["POST"])
def analyze_photo():
    data = request.get_json(force=True)
    url = data.get("image_url")
    if not url:
        return jsonify({"error": "image_url required"}), 400
    sys = ("Ты нутрициолог. Определи продукты на фото, массу и калории. Верни JSON "
           "как в /count-calories.")
    messages = [{"role":"system","content":sys},{"role":"user","content":[
        {"type":"text","text":"Определи продукты по фото."},
        {"type":"image_url","image_url":{"url":url}}
    ]}]
    r = requests.post(OPENAI_CHAT_URL, headers={"Authorization":f"Bearer {OPENAI_API_KEY}","Content-Type":"application/json"},
                      json={"model":"gpt-4o-mini","messages":messages}, timeout=180)
    content = r.json()["choices"][0]["message"]["content"]
    return jsonify(coerce_json(content))

@app.route("/add-entry", methods=["POST"])
def add_entry():
    data = request.get_json(force=True)
    sheet_id = os.environ.get("SHEET_ID")
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sheet_id or not sa_json:
        return jsonify({"error":"Google Sheets not configured"}), 501
    creds = Credentials.from_service_account_info(json.loads(sa_json), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    ws = gspread.authorize(creds).open_by_key(sheet_id).sheet1
    ws.append_row([data.get("timestamp"), data.get("user_id"), data.get("text"),
                   data.get("totals",{}).get("kcal")])
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
