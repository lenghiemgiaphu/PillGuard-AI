from openai import OpenAI

def check_drug_interaction(old_drugs: str, new_drugs: str, api_key: str) -> str:
    """Kiểm tra tương tác thuốc (DDI) giữa thuốc đang dùng và thuốc mới bằng OpenAI GPT.
        Trả về văn bản cảnh báo bằng tiếng Việt, dễ hiểu cho người già.
    
        LƯU Ý AN TOÀN: Đây là kiểm tra bằng AI ngôn ngữ, KHÔNG được đối chiếu với
        cơ sở dữ liệu dược lý chính thức. Không nên dùng làm căn cứ y khoa duy nhất —
        luôn khuyến khích người dùng hỏi lại dược sĩ/bác sĩ với các trường hợp
        CẦN THẬN TRỌNG hoặc NGUY HIỂM."""
    if not api_key:
        return "Chưa cấu hình OPENAI_API_KEY nên không thể kiểm tra tương tác thuốc."

    if not old_drugs.strip() or not new_drugs.strip():
        return "Vui lòng cung cấp đầy đủ thông tin thuốc đang dùng và thuốc mới."

    client = OpenAI(api_key=api_key)

    prompt = f"""Bạn là dược sĩ lâm sàng AI hỗ trợ người cao tuổi tại Việt Nam.

Thuốc đang dùng: {old_drugs}
Thuốc mới định dùng thêm: {new_drugs}

Trả lời ngắn gọn, dễ hiểu bằng tiếng Việt (nếu người dùng sử dụng tiếng Anh, hãy trả lời bằng tiếng Anh), đúng cấu trúc sau (không dùng ký tự đặc biệt như *, #):

Mức độ an toàn: [AN TOÀN / CẦN THẬN TRỌNG / NGUY HIỂM - KHÔNG NÊN DÙNG CHUNG]
Lý do: [1-2 câu ngắn gọn]
Khuyến nghị: [nên uống cách nhau bao lâu, có cần hỏi bác sĩ/dược sĩ không]"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Bạn là dược sĩ tư vấn an toàn thuốc."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Lỗi kiểm tra DDI: {e}")
        return "Xin lỗi, hiện tại AI không thể kiểm tra tương tác thuốc."