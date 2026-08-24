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

# Thiết lập đường dẫn hệ thống
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

# Import các công cụ hỗ trợ
from ocr_engine import process_handwriting_ocr, make_tts_friendly, parse_ocr_json
from openai_ai import check_drug_interaction
from worker import speech_to_text, text_to_speech, openai_process_message, generate_health_memo

app = Flask(__name__)
CORS(app)

# Cấu hình API Key và Thư mục lưu trữ
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MEMO_FOLDER = os.path.join(os.getcwd(), 'memos')
os.makedirs(MEMO_FOLDER, exist_ok=True)

@app.route("/")
def index():
    return render_template("index.html")

# --- 1. XỬ LÝ ĐƠN THUỐC (OCR) ---
@app.route('/api/ocr', methods=['POST'])
def handle_ocr():
    try:
        file = request.files.get('image') or request.files.get('file')
        if not file:
            return jsonify({'success': False, 'error': 'Bà ơi, con không tìm thấy ảnh ạ!'}), 400

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
        print(f"Lỗi OCR: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# --- 2. TRỢ LÝ GIỌNG NÓI & CHAT ---
@app.route('/process-message', methods=['POST'])
def process_message_route():
    try:
        data = request.get_json() or {}
        user_message = data.get('userMessage', '')
        voice = data.get('voice', 'vi-VN-HoaiMyNeural')

        # Gọi AI xử lý tin nhắn
        openai_response_text = openai_process_message(user_message)
        
        # Chuyển chữ thành giọng nói
        audio_data = text_to_speech(openai_response_text, voice)
        openai_response_speech = base64.b64encode(audio_data).decode('utf-8')

        return jsonify({
            "openaiResponseText": openai_response_text,
            "openaiResponseSpeech": openai_response_speech,
        })
    except Exception as e:
        print(f"Lỗi Chat: {e}")
        return jsonify({"openaiResponseText": "Thưa bà, con gặp chút lỗi kết nối, bà nói lại nhé ạ!", "error": str(e)}), 500

# --- 3. QUẢN LÝ NHẬT KÝ (MEMO) ---

# Thêm hàm liệt kê danh sách nhật ký (Sửa lỗi 404)
@app.route('/api/list-memos', methods=['GET'])
def list_memos():
    try:
        if not os.path.exists(MEMO_FOLDER):
            return jsonify({'success': True, 'files': []})
        files = [f for f in os.listdir(MEMO_FOLDER) if f.endswith('.txt')]
        return jsonify({'success': True, 'files': sorted(files, reverse=True)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Thêm hàm đọc nội dung một bản nhật ký
@app.route('/api/get-memo/<filename>', methods=['GET'])
def get_memo(filename):
    try:
        return send_from_directory(MEMO_FOLDER, filename)
    except Exception as e:
        return str(e), 404

@app.route("/api/generate-memo", methods=["POST"])
def handle_generate_memo():
    try:
        data = request.json or {}
        conversation = data.get("conversation", "")
        memo_data = generate_health_memo(conversation)
        return jsonify({"success": True, "memo": memo_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/save-memo', methods=['POST'])
def save_memo():
    try:
        data = request.json or {}
        raw_date = data.get('date', 'unknown').strip()
        safe_date = re.sub(r'[/\\?%*:|"<> ]', '-', raw_date)
        filename = f"Memo_{safe_date}_{data.get('mainConcern', 'General')[:15]}.txt"
        filepath = os.path.join(MEMO_FOLDER, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"NHẬT KÝ SỨC KHỎE\nNgày: {raw_date}\n\nVấn đề: {data.get('mainConcern')}\nTriệu chứng: {data.get('symptoms')}")
            
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# --- 4. CHUYỂN GIỌNG NÓI THÀNH CHỮ ---
@app.route('/speech-to-text', methods=['POST'])
def stt_route():
    try:
        audio_binary = request.data
        text = speech_to_text(audio_binary)
        return jsonify({'text': text})
    except Exception as e:
        return jsonify({'text': '', 'error': str(e)})

if __name__ == "__main__":
    # Render yêu cầu chạy trên port do họ cấp, hoặc mặc định 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
