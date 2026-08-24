import os
import json
import io
import base64
from PIL import Image
from openai import OpenAI

def process_handwriting_ocr(image: Image.Image, api_key: str) -> str:
    """Nhận diện chữ viết tay trên đơn thuốc qua OpenAI Vision API."""
    if not api_key:
        raise RuntimeError("Thiếu OPENAI_API_KEY. Hãy đặt biến môi trường OPENAI_API_KEY.")

    client = OpenAI(api_key=api_key)

    # Chuyển đổi ảnh PIL sang Base64
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

    prompt = """
    Nhiệm vụ: Trích xuất văn bản (OCR) thuần túy từ hình ảnh giấy tờ cá nhân để lưu trữ hồ sơ.
    Đây là tác vụ chuyển đổi hình ảnh thành văn bản, KHÔNG PHẢI tư vấn hay chẩn đoán y tế.
    Hãy đọc hình ảnh đơn thuốc này và trích xuất danh sách thuốc dưới dạng mảng JSON (JSON Array).
    Bỏ qua thông tin bệnh nhân, tên bác sĩ hoặc tiêu đề đơn thuốc.
    Liều lượng thuốc, hướng dẫn và thời gian uống đều sẽ nằm ở dòng phía dưới tên thuốc.
    CẤM BỊA THÊM THÔNG TIN.
    BƯỚC 1 - TRÍCH XUẤT NGUYÊN VĂN (RAW TEXT):
    Hãy chép lại TOÀN BỘ các chữ/dòng xuất hiện trong ảnh từ trên xuống dưới vào trường "raw_text_extracted". 
    - Giữ nguyên chữ in, chữ viết tay, tên thuốc, số lượng, ký hiệu (vd: S1, T1, u30p SA...).
    - Tuyệt đối không tự sửa hay đoán chữ nếu không nhìn rõ.

    BƯỚC 2 - CHUYỂN ĐỔI SANG JSON:
    Dựa VÀO CHÍNH TRƯỜNG "raw_text_extracted" BƯỚC 1, hãy sắp xếp lại thông tin thành mảng JSON.
    Định dạng JSON yêu cầu:
    [
        "raw_text_extracted":"Toàn bộ văn bản thô đọc được"
      {
        "name": "Tên thuốc & Hàm lượng",
        "dose": "Liều lượng (tìm mỗi lần uống. lưu ý là số có thể nhiều hơn 1 viên.)",
        "time": "Thời gian uống (CÓ 4 BUỔI LÀ SÁNG, TRƯA, CHIỀU VÀ TỐI. Tìm trong dòng đó, nếu không có bữa nào thì ghi "None". Ngoài 4 buổi ấy, ĐỪNG GHI BẤT KÌ CÁI GÌ KHÁC.)",
        "note": "Hướng dẫn (VD: Uống sau bữa ăn, uống cách ngày, v.v.)"
      }
    ]
    Cần đảm bảo chỉ trả về JSON hợp lệ, không kèm văn bản giải thích.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "high"}
                        }
                    ]
                }
            ],
            temperature=0.0,
            max_tokens=4000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Lỗi OpenAI OCR: {e}")
        return "[]"


def parse_ocr_json(raw_text: str):
    """Chuyển JSON trả về từ OpenAI thành list các thuốc."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text.split("\n", 1)[-1]
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []


def make_tts_friendly(raw_text: str) -> str:
    """Chuyển kết quả OCR thành câu nói rõ ràng cho TTS."""
    drugs = parse_ocr_json(raw_text)

    if drugs:
        spoken_sentences = []
        for drug in drugs:
            ten_thuoc = (drug.get("name") or "").strip()
            lieu_luong = (drug.get("dose") or "").strip()
            cach_dung = (drug.get("time") or "").strip()
            ghi_chu = (drug.get("note") or "").strip()

            sentence = f"Thuốc {ten_thuoc}. Liều dùng: {lieu_luong}. Thời gian uống: {cach_dung}."
            if ghi_chu:
                sentence += f" Ghi chú: {ghi_chu}."
            spoken_sentences.append(sentence)
        return " ... ".join(spoken_sentences)

    lines = raw_text.strip().split("\n")
    clean_lines = [line.replace("-", "").strip() for line in lines if line.strip()]
    return " ... ".join(clean_lines)