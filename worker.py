import os
import sys
import asyncio
import tempfile
import json
import re
from openai import OpenAI
import edge_tts

# Lấy API Key từ biến môi trường Render
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("⚠️ Chưa đặt biến môi trường OPENAI_API_KEY!")

client = OpenAI(api_key=OPENAI_API_KEY)


def speech_to_text(audio_binary):
    if not audio_binary:
        return ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as temp_audio:
            temp_audio.write(audio_binary)
            temp_audio_path = temp_audio.name

        with open(temp_audio_path, "rb") as audio_file:
            transcript_response = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,
                language="vi"
            )
            
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
            
        return transcript_response.text
    except Exception as e:
        print(f"❌ Lỗi khi chuyển Speech-to-Text: {e}")
        return ""


def openai_process_message(user_message):
    """Sử dụng GPT-4o-mini tư vấn y tế"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Bạn là PillGuard AI, trợ lý y tế thông minh tư vấn về thuốc. Trả lời ngắn gọn, chính xác và dễ hiểu bằng tiếng Việt hoặc tiếng Anh, TÙY VÀO NGƯỜI DÙNG NÓI TIẾNG NÀO."
                },
                {"role": "user", "content": user_message}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ Lỗi OpenAI GPT: {e}")
        return "Xin lỗi, hiện tại hệ thống AI đang bận. Bạn vui lòng thử lại sau."


def text_to_speech(text, voice="vi-VN-HoaiMyNeural"):
    """Tạo audio MP3 tối ưu tốc độ bằng cách làm sạch văn bản & tăng Timeout"""
    if not text or not text.strip():
        return b""

    # 1. Làm sạch văn bản: Bỏ xuống dòng, khoảng trắng thừa để TTS xử lý siêu nhanh
    clean_text = re.sub(r'\s+', ' ', text).strip()

    async def _generate():
        communicate = edge_tts.Communicate(clean_text, voice)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_mp3:
            temp_mp3_path = temp_mp3.name
        await communicate.save(temp_mp3_path)
        
        with open(temp_mp3_path, "rb") as f:
            data = f.read()

        if os.path.exists(temp_mp3_path):
            os.remove(temp_mp3_path)
        return data

    try:
        # 2. Sử dụng asyncio.run an toàn cho Python 3.11+
        return asyncio.run(_generate())
    except Exception as e:
        print(f"❌ Lỗi Text-to-Speech (Edge-TTS): {e}")
        return b""


def generate_health_memo(conversation_text):
    if not conversation_text or not conversation_text.strip():
        return None

    prompt = f"""
Bạn là trợ lý y tế chuyên trích xuất thông tin sức khỏe thành Memo ngắn gọn.
Hãy trích xuất thông tin từ đoạn hội thoại dưới đây thành định dạng JSON với các khóa (keys) tiếng Việt:

JSON Output Format:
{{
  "date": "Ngày xảy ra (Ví dụ: 16/08/2026 hoặc 'Không đề cập')",
  "main_concern": "Vấn đề chính / Bận tâm lớn nhất",
  "symptoms": "Các triệu chứng xuất hiện",
  "timing_duration": "Thời điểm bị & Thời gian kéo dài",
  "severity": "Mức độ nghiêm trọng",
  "medication_mentioned": "Thuốc được đề cập / Đã uống",
  "side_effects": "Tác dụng phụ có thể có",
  "what_helped": "Cách xử lý / Việc đã làm giúp dịu bớt",
  "questions_for_doctor": "Câu hỏi cần hỏi Bác sĩ hoặc Người chăm sóc",
  "follow_up": "Theo dõi tiếp theo"
}}

NGUYÊN TẮC AN TOÀN BẮT BUỘC:
1. KHÔNG TỰ CHẨN ĐOÁN BỆNH.
2. KHÔNG TỰ Ý ĐỀ XUẤT ĐỔI LIỀU HOẶC NGỪNG THUỐC.
3. KHÔNG TỰ NGHĨ RA THÔNG TIN KHÔNG CÓ TRONG HỘI THOẠI.
4. Nếu thông tin nào không xuất hiện trong chat, điền chính xác từ: "Không đề cập".
5. Ngôn ngữ sử dụng: Tiếng Việt ngắn gọn, khách quan.

Đoạn hội thoại:
\"\"\"
{conversation_text}
\"\"\"
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Bạn là AI trích xuất dữ liệu Health Memo an toàn và chính xác."},
                {"role": "user", "content": prompt}
            ]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ Lỗi trích xuất Health Memo: {e}")
        return None
