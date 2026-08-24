import os
import sys
import json
import base64
import io
import re
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from PIL import Image

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from ocr_engine import process_handwriting_ocr, make_tts_friendly, parse_ocr_json
from openai_ai import check_drug_interaction
from worker import speech_to_text, text_to_speech, openai_process_message, generate_health_memo

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Lấy OpenAI API key từ môi trường
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("⚠️ Chưa đặt biến môi trường OPENAI_API_KEY!")

MEMO_FOLDER = os.path.join(os.getcwd(), 'memos')
os.makedirs(MEMO_FOLDER, exist_ok=True)
@app.route("/")
def index():
    return render_template("index.html")


@app.route('/api/ocr', methods=['POST'])
def handle_ocr():
    try:
        file = request.files.get('file') or request.files.get('image')
        if not file:
            return jsonify({'success': False, 'error': 'No file found under key "file" or "image"'}), 400

        image = Image.open(io.BytesIO(file.read()))
        raw_text = process_handwriting_ocr(image, OPENAI_API_KEY)
        parsed_drugs = parse_ocr_json(raw_text)
        tts_text = make_tts_friendly(raw_text)

        return jsonify({
            'success': True,
            'raw_text': raw_text,
            'drugs': parsed_drugs,
            'tts_text': tts_text
        })
    except Exception as e:
        print(f"❌ Server Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/check-ddi", methods=["POST"])
def handle_ddi():
    try:
        data = request.json or {}
        old_drugs = data.get("old_drugs", "")
        new_drugs = data.get("new_drugs", "")

        result = check_drug_interaction(old_drugs, new_drugs, OPENAI_API_KEY)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        print(f"❌ Lỗi kiểm tra DDI: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/speech-to-text', methods=['POST'])
def speech_to_text_route():
    audio_binary = request.data
    text = speech_to_text(audio_binary)
    return jsonify({'text': text})


@app.route('/process-message', methods=['POST'])
def process_message_route():
    data = request.get_json() or {}
    user_message = data.get('userMessage', '')
    voice = data.get('voice', 'vi-VN-HoaiMyNeural')

    openai_response_text = openai_process_message(user_message)
    openai_response_text = os.linesep.join([s for s in openai_response_text.splitlines() if s])

    openai_response_speech = text_to_speech(openai_response_text, voice)
    openai_response_speech = base64.b64encode(openai_response_speech).decode('utf-8')

    return jsonify({
        "openaiResponseText": openai_response_text,
        "openaiResponseSpeech": openai_response_speech,
    })


@app.route("/api/generate-memo", methods=["POST"])
def handle_generate_memo():
    try:
        data = request.json or {}
        conversation = data.get("conversation", "")

        if not conversation:
            return jsonify({"success": False, "error": "Chưa có nội dung hội thoại!"}), 400

        memo_data = generate_health_memo(conversation)
        if memo_data:
            return jsonify({"success": True, "memo": memo_data})
        return jsonify({"success": False, "error": "Không thể trích xuất Memo từ AI."}), 500
    except Exception as e:
        print(f"❌ Lỗi API Memo: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
@app.route('/api/search-memos', methods=['GET'])
def search_memos():
    query = request.args.get('q', '').lower().strip()
    matches = []

    if not os.path.exists(MEMO_FOLDER):
        return jsonify({'success': True, 'results': []})

    for filename in os.listdir(MEMO_FOLDER):
        if filename.endswith('.txt'):
            filepath = os.path.join(MEMO_FOLDER, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Search inside both the filename and the full text content
                if not query or query in filename.lower() or query in content.lower():
                    matches.append({
                        'filename': filename,
                        'content': content
                    })

    return jsonify({'success': True, 'count': len(matches), 'results': matches})
@app.route('/api/save-memo', methods=['POST'])
def save_memo():
    data = request.json or {}

    # 1. Sanitize the date for filename compatibility (e.g., "2026-08-23")
    raw_date = data.get('date', 'unknown-date').strip()
    safe_date = re.sub(r'[/\\?%*:|"<> ]', '-', raw_date)

    # 2. Extract and sanitize main concern (max 20 chars)
    raw_concern = data.get('mainConcern', 'General').strip()
    safe_concern = re.sub(r'[^a-zA-Z0-9]', '_', raw_concern)[:20].strip('_') or "General"

    # 3. Find existing memos saved on the same date and get highest index
    existing_indices = []
    pattern = re.compile(rf"^Memo_{re.escape(safe_date)}_\((\d+)\)")

    for existing_file in os.listdir(MEMO_FOLDER):
        match = pattern.match(existing_file)
        if match:
            existing_indices.append(int(match.group(1)))

    # 4. Calculate next index (defaults to 1 if no files exist for today)
    next_index = max(existing_indices, default=0) + 1

    # 5. New Filename Pattern: Memo_YYYY-MM-DD_(1)_Headache.txt
    filename = f"Memo_{safe_date}_({next_index})_{raw_concern}.txt"
    filepath = os.path.join(MEMO_FOLDER, filename)

    # 6. Build file content
    content = f"""==================================================
           NHẬT KÝ SỨC KHỎE (HEALTH MEMO)
==================================================
📅 Ngày ghi nhận: {data.get('date', '')}
🚨 Mức độ nghiêm trọng: {data.get('severity', '')}

🎯 VẤN ĐỀ CHÍNH (MAIN CONCERN):
{data.get('mainConcern', '')}

🤒 TRIỆU CHỨNG XUẤT HIỆN (SYMPTOMS):
{data.get('symptoms', '')}

⏱️ THỜI ĐIỂM & KÉO DÀI:
{data.get('timing', '')}

💊 THUỐC LIÊN QUAN:
{data.get('medication', '')}

⚠️ TÁC DỤNG PHỤ (NGHI NGỜ):
{data.get('sideEffects', '')}

🧘 MẸO / VIỆC ĐÃ LÀM ĐỂ ĐỞ ĐAU:
{data.get('whatHelped', '')}

❓ CÂU HỎI CẦN HỎI BÁC SĨ (QUESTIONS FOR DOCTOR):
{data.get('questions', '')}

--------------------------------------------------
⚠️ CẢNH BÁO: Memo này chỉ ghi nhận thông tin bệnh nhân
trình bày, KHÔNG PHẢI LÀ CHẨN ĐOÁN Y KHOA.
=================================================="""

    # Save to disk
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    return jsonify({'success': True, 'filename': filename, 'index': next_index})

if __name__ == "__main__":
    app.run(debug=True, port=5000, host='0.0.0.0')
