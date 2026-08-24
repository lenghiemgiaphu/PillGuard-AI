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

# Lấy API key từ biến môi trường của Render
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

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
            return jsonify({'success': False, 'error': 'Không tìm thấy file hình ảnh trong request!'}), 400

        image = Image.open(io.BytesIO(file.read()))
        # Dùng OPENAI_API_KEY (hoặc GEMINI_API_KEY tùy cấu hình của bạn)
        raw_text = process_handwriting_ocr(image, OPENAI_API_KEY)
        
        try:
            parsed_drugs = parse_ocr_json(raw_text)
        except Exception:
            parsed_drugs = []
            
        try:
            tts_text = make_tts_friendly(raw_text)
        except Exception:
            tts_text = raw_text

        return jsonify({
            'success': True,
            'raw_text': raw_text,
            'drugs': parsed_drugs,
            'tts_text': tts_text
        })
    except Exception as e:
        print(f"❌ Server OCR Error: {e}")
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
    try:
        audio_binary = request.data
        if not audio_binary:
            return jsonify({'text': ''})
        text = speech_to_text(audio_binary)
        return jsonify({'text': text})
    except Exception as e:
        print(f"❌ Lỗi Speech-to-Text: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/process-message', methods=['POST'])
def process_message_route():
    try:
        data = request.get_json() or {}
        user_message = data.get('userMessage', '')
        voice = data.get('voice', 'vi-VN-HoaiMyNeural')

        openai_response_text = openai_process_message(user_message)
        openai_response_text = os.linesep.join([s for s in openai_response_text.splitlines() if s.strip()])

        openai_response_speech = text_to_speech(openai_response_text, voice)
        openai_response_speech = base64.b64encode(openai_response_speech).decode('utf-8')

        return jsonify({
            "openaiResponseText": openai_response_text,
            "openaiResponseSpeech": openai_response_speech,
        })
    except Exception as e:
        print(f"❌ Lỗi Process Message: {e}")
        return jsonify({"error": str(e)}), 500


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
    try:
        query = request.args.get('q', '').lower().strip()
        matches = []

        if not os.path.exists(MEMO_FOLDER):
            return jsonify({'success': True, 'results': []})

        for filename in os.listdir(MEMO_FOLDER):
            if filename.endswith('.txt'):
                filepath = os.path.join(MEMO_FOLDER, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if not query or query in filename.lower() or query in content.lower():
                        matches.append({
                            'filename': filename,
                            'content': content
                        })

        return jsonify({'success': True, 'count': len(matches), 'results': matches})
    except Exception as e:
        print(f"❌ Lỗi Search Memos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save-memo', methods=['POST'])
def save_memo():
    try:
        data = request.json or {}

        # 1. Chuẩn hóa ngày tháng
        raw_date = data.get('date', 'unknown-date').strip()
        safe_date = re.sub(r'[/\\?%*:|"<> ]', '-', raw_date)

        # 2. Chuẩn hóa vấn đề chính cho tên file (dùng safe_concern thay vì raw_concern để tránh lỗi ký tự tiếng Việt/đặc biệt)
        raw_concern = data.get('mainConcern', 'General').strip()
        safe_concern = re.sub(r'[^a-zA-Z0-9]', '_', raw_concern)[:20].strip('_') or "General"

        # 3. Đếm số thứ tự file
        existing_indices = []
        pattern = re.compile(rf"^Memo_{re.escape(safe_date)}_\((\d+)\)")

        for existing_file in os.listdir(MEMO_FOLDER):
            match = pattern.match(existing_file)
            if match:
                existing_indices.append(int(match.group(1)))

        next_index = max(existing_indices, default=0) + 1

        # 4. Tên file an toàn
        filename = f"Memo_{safe_date}_({next_index})_{safe_concern}.txt"
        filepath = os.path.join(MEMO_FOLDER, filename)

        # 5. Khởi tạo nội dung phẳng (loại bỏ khoảng trắng indent thụt đầu dòng)
        content = (
            "==================================================\n"
            "               NHẬT KÝ SỨC KHỎE (HEALTH MEMO)\n"
            "==================================================\n"
            f"📅 Ngày ghi nhận: {data.get('date', '')}\n"
            f"🚨 Mức độ nghiêm trọng: {data.get('severity', '')}\n\n"
            "🎯 VẤN ĐỀ CHÍNH (MAIN CONCERN):\n"
            f"{data.get('mainConcern', '')}\n\n"
            "🤒 TRIỆU CHỨNG XUẤT HIỆN (SYMPTOMS):\n"
            f"{data.get('symptoms', '')}\n\n"
            "⏱️ THỜI ĐIỂM & KÉO DÀI:\n"
            f"{data.get('timing', '')}\n\n"
            "💊 THUỐC LIÊN QUAN:\n"
            f"{data.get('medication', '')}\n\n"
            "⚠️ TÁC DỤNG PHỤ (NGHI NGỜ):\n"
            f"{data.get('sideEffects', '')}\n\n"
            "🧘 MẸO / VIỆC ĐÃ LÀM ĐỂ ĐỞ ĐAU:\n"
            f"{data.get('whatHelped', '')}\n\n"
            "❓ CÂU HỎI CẦN HỎI BÁC SĨ (QUESTIONS FOR DOCTOR):\n"
            f"{data.get('questions', '')}\n\n"
            "--------------------------------------------------\n"
            "⚠️ CẢNH BÁO: Memo này chỉ ghi nhận thông tin bệnh nhân\n"
            "trình bày, KHÔNG PHẢI LÀ CHẨN ĐOÁN Y KHOA.\n"
            "=================================================="
        )

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return jsonify({'success': True, 'filename': filename, 'index': next_index})
    except Exception as e:
        print(f"❌ Lỗi Save Memo: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000, host='0.0.0.0')
