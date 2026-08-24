/* ==========================================
   PILLGUARD AI - MAIN INTERACTIVE & VOICE LOGIC
   ========================================== */

let lightMode = false;
let recorder = null;
let recording = false;
let voiceOption = "vi-VN-HoaiMyNeural";
const responses = [];
const botRepeatButtonIDToIndexMap = {};
const userRepeatButtonIDToRecordingMap = {};
const baseUrl = window.location.origin;

// Hàm sleep delay
const sleep = (time) => new Promise((resolve) => setTimeout(resolve, time));

/* ==========================================
   1. XỬ LÝ FILE & MODAL KIỂM TRA MẮT NGƯỜI (KHUNG 1)
   ========================================== */

// Xử lý khi chọn file đơn thuốc (Khung 1) và gửi lên Flask Server
async function handlePrescriptionUpload(event) {
  const file = event.target.files[0];
  const nameLabel = document.getElementById("prescription-file-name");
  
  if (!file) return;

  if (nameLabel) {
    nameLabel.innerText = "⏳ Đang phân tích OCR: " + file.name;
  }

  // Tạo FormData để đóng gói file gửi lên Flask API
  const formData = new FormData();
  formData.append("image", file);

  try {
    speakText("Hệ thống đang quét đơn thuốc, vui lòng đợi trong giây lát.");

    // Gửi yêu cầu tới API Flask
    const response = await fetch("/api/ocr", {
      method: "POST",
      body: formData
    });

    const data = await response.json();

    if (data.success) {
      if (nameLabel) {
        nameLabel.innerText = "✅ Đã đọc xong: " + file.name;
      }

      // Phát âm thanh đọc kết quả TTS
      speakText(data.tts_text || "Đã trích xuất xong đơn thuốc.");

      // Cập nhật dữ liệu OCR nhận được vào bảng trong Modal kiểm tra
      populateModalWithOCR(data.raw_text);

      // Mở Modal kiểm tra cho con người xác nhận (Human-in-the-loop)
      openVerificationModal();
    } else {
      alert("Lỗi khi đọc đơn thuốc: " + data.error);
      if (nameLabel) nameLabel.innerText = "❌ Lỗi khi đọc ảnh";
    }
  } catch (error) {
    console.error("Lỗi gửi ảnh OCR:", error);
    alert("Không thể kết nối tới máy chủ Flask!");
    if (nameLabel) nameLabel.innerText = "❌ Lỗi kết nối";
  }
}

function populateModalWithOCR(rawText) {
  const tbody = document.getElementById('modal-drug-list');
  if (!tbody) return;

  tbody.innerHTML = '';
  if (!rawText) return;

  let items = [];

  try {
    if (typeof rawText === 'string') {
      const cleanJson = rawText.replace(/```json/g, '').replace(/```/g, '').trim();
      items = JSON.parse(cleanJson);
    } else if (Array.isArray(rawText)) {
      items = rawText;
    }
  } catch (e) {
    console.warn("Dự phòng tách dòng:", e);
    const lines = rawText.split('\n').filter(line => line.trim() !== '');
    items = lines.map(line => ({
      name: line.trim(),
      dose: "1 viên",
      time: "Sáng",
      note: "Uống sau ăn"
    }));
  }

  items.forEach(item => {
    const name = item.name || item.medication || '';
    const dose = item.dose || item.dosage || '1 viên';
    const time = item.time || item.frequency || 'Sáng';
    const note = item.note || item.instructions || 'Uống sau khi ăn';

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="p-1.5"><input type="text" value="${name.replace(/"/g, '&quot;')}" class="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-xs focus:border-yellow-400 outline-none"></td>
      <td class="p-1.5"><input type="text" value="${dose.replace(/"/g, '&quot;')}" class="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-xs focus:border-yellow-400 outline-none"></td>
      <td class="p-1.5"><input type="text" value="${time.replace(/"/g, '&quot;')}" class="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-xs focus:border-yellow-400 outline-none"></td>
      <td class="p-1.5"><input type="text" value="${note.replace(/"/g, '&quot;')}" class="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-xs focus:border-yellow-400 outline-none"></td>
      <td class="p-1.5 text-center"><button onclick="this.closest('tr').remove()" class="text-rose-400 hover:text-rose-300 font-bold px-1">✕</button></td>
    `;
    tbody.appendChild(tr);
  });
}

// 2. Chuyển dữ liệu từ Modal sang Bảng Lịch Sử chính (Tách biệt Thời gian và Ghi chú AI)
function applyModalChanges() {
  const rows = document.querySelectorAll('#modal-drug-list tr');
  const historyTableBody = document.getElementById('history-table-body');
  if (!historyTableBody) return;

  historyTableBody.innerHTML = '';

  rows.forEach((row) => {
    const inputs = row.querySelectorAll('input');
    if (inputs.length >= 4) {
      const nameDose = `${inputs[0].value} (${inputs[1].value})`;
      const time = inputs[2].value;
      const note = inputs[3].value;

      const newRow = document.createElement('tr');
      newRow.className = "hover:bg-gray-800/40 transition";
      newRow.innerHTML = `
        <td class="p-3 font-bold text-blue-400">Ngày 1</td>
        <td class="p-3 font-semibold text-white">${nameDose}</td>
        <td class="p-3 font-mono text-yellow-400 font-bold">${time}</td>
        <td class="p-3 text-gray-400">${note}</td>
        <td class="p-3 text-center">
          <input type="checkbox" onchange="toggleTaken(this)" class="w-5 h-5 accent-emerald-500 cursor-pointer rounded">
        </td>
      `;
      historyTableBody.appendChild(newRow);
    }
  });

  closeVerificationModal();
  speakText("Đã xác nhận và lưu đơn thuốc vào bảng lịch sử thành công.");
}

// 3. Đọc dữ liệu lịch sử chuẩn xác cho Context AI Soi vỉ thuốc
function getPrescriptionContext() {
  const rows = document.querySelectorAll('#history-table-body tr');
  let contextText = "";
  rows.forEach((row, idx) => {
    const cols = row.querySelectorAll('td');
    if (cols.length >= 4) {
      contextText += `${idx + 1}. ${cols[1].innerText} - Thời gian: ${cols[2].innerText} - Ghi chú: ${cols[3].innerText}\n`;
    }
  });
  return contextText || "Chưa có dữ liệu đơn thuốc.";
}

// Xử lý khi tải ảnh vỉ thuốc qua nút Upload ở Khung 2
async function handleDailyFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;

  updateDrugInfoUI("⏳ Đang nhận diện...", "⏳ Đang tra cứu...", "⏳ Đang tra cứu...");
  speakText("Đang phân tích vỉ thuốc, vui lòng chờ.");

  const formData = new FormData();
  formData.append("image", file);
  formData.append("prescription_context", getPrescriptionContext());

  try {
    const response = await fetch("/api/scan-pill", {
      method: "POST",
      body: formData
    });

    const data = await response.json();
    if (data.success) {
      parseAndDisplayPillResult(data.result);
    } else {
      updateDrugInfoUI("❌ Lỗi nhận diện", "--", "--");
      alert("Không thể soi vỉ thuốc: " + data.error);
    }
  } catch (err) {
    console.error("Lỗi scan pill:", err);
    updateDrugInfoUI("❌ Lỗi kết nối", "--", "--");
  }
}

// Hàm hỗ trợ tách chuỗi trả về từ Gemini và dán vào 3 ô
function parseAndDisplayPillResult(resultText) {
  let name = "--";
  let dose = "--";
  let time = "--";

  const lines = resultText.split("\n");
  lines.forEach(line => {
    if (line.includes("1. Tên thuốc:") || line.includes("Tên thuốc:")) {
      name = line.split(":")[1]?.trim() || "--";
    } else if (line.includes("2. Liều lượng:") || line.includes("Liều lượng:")) {
      dose = line.split(":")[1]?.trim() || "--";
    } else if (line.includes("3. Thời gian sử dụng:") || line.includes("Thời gian:")) {
      time = line.split(":")[1]?.trim() || "--";
    }
  });

  updateDrugInfoUI(name, dose, time);
  speakText(`Thuốc ${name}. Liều lượng: ${dose}. Thời gian uống: ${time}.`);
}

// Hàm cập nhật Giao diện 3 ô Khung 2
function updateDrugInfoUI(name, dose, time) {
  const drugName = document.getElementById("drug-name");
  const drugDose = document.getElementById("drug-dose");
  const drugTime = document.getElementById("drug-time");

  if (drugName) drugName.innerText = name;
  if (drugDose) drugDose.innerText = dose;
  if (drugTime) drugTime.innerText = time;
}

// Đánh dấu trạng thái đã uống thuốc
function toggleTaken(checkbox) {
  const row = checkbox.closest("tr");
  if (checkbox.checked) {
    row.classList.add("opacity-50", "line-through");
    speakText("Đã ghi nhận uống thuốc thành công.");
  } else {
    row.classList.remove("opacity-50", "line-through");
  }
}

// Đọc câu thông báo nhanh qua Web Speech API
function speakText(text) {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    
    // Set language based on selected voiceOption prefix
    if (typeof voiceOption !== 'undefined' && voiceOption.startsWith('en-')) {
      utterance.lang = 'en-US';
    } else {
      utterance.lang = 'vi-VN';
    }

    utterance.rate = 0.9;
    window.speechSynthesis.speak(utterance);
  }
}

/* ==========================================
   3. TRỢ LÝ GIỌNG NÓI PILLGUARD (KHUNG 3: OPENAI & TTS)
   ========================================== */

// Hiển thị / Ẩn Loading Animation
async function showBotLoadingAnimation() {
  await sleep(300);
  $(".loading-animation").not(".my-loading").show();
}

function hideBotLoadingAnimation() {
  $(".loading-animation").not(".my-loading").hide();
}

async function showUserLoadingAnimation() {
  await sleep(100);
  $(".loading-animation.my-loading").show();
}

function hideUserLoadingAnimation() {
  $(".loading-animation.my-loading").hide();
}

// API Call: Speech To Text
const getSpeechToText = async (userRecording) => {
  try {
    if (!userRecording || !userRecording.audioBlob) {
      return "Không có dữ liệu âm thanh.";
    }

    let response = await fetch(baseUrl + "/speech-to-text", {
      method: "POST",
      body: userRecording.audioBlob,
    });
    response = await response.json();
    return response.text || "Không thể nhận diện giọng nói.";
  } catch (error) {
    console.error("Lỗi Speech-to-Text:", error);
    return "Lỗi kết nối Speech-to-Text.";
  }
};

// API Call: Process Message (OpenAI / Gemini + TTS)
const processUserMessage = async (userMessage) => {
  try {
    let response = await fetch(baseUrl + "/process-message", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ userMessage: userMessage, voice: voiceOption }),
    });
    response = await response.json();
    return response;
  } catch (error) {
    console.error("Lỗi Process Message:", error);
    return {
      openaiResponseText: "Rất tiếc, đã có lỗi kết nối máy chủ backend.",
      openaiResponseSpeech: ""
    };
  }
};

// Làm sạch input nhập vào
const cleanTextInput = (value) => {
  return value
    .trim()
    .replace(/[\n\t]/g, "")
    .replace(/<[^>]*>/g, "")
    .replace(/[<>&;]/g, "");
};

// Record Audio từ Microphone
const recordAudio = () => {
  return new Promise(async (resolve) => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    const audioChunks = [];

    mediaRecorder.addEventListener("dataavailable", (event) => {
      audioChunks.push(event.data);
    });

    const start = () => mediaRecorder.start();

    const stop = () =>
      new Promise((resolve) => {
        mediaRecorder.addEventListener("stop", () => {
          const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
          const audioUrl = URL.createObjectURL(audioBlob);
          const audio = new Audio(audioUrl);
          const play = () => audio.play();
          resolve({ audioBlob, audioUrl, play });
        });

        mediaRecorder.stop();
      });

    resolve({ start, stop });
  });
};

const toggleRecording = async () => {
  if (!recording) {
    recorder = await recordAudio();
    recording = true;
    recorder.start();
  } else {
    recording = false; // Tự động cập nhật lại trạng thái khi tắt
    const audio = await recorder.stop();
    await sleep(500);
    return audio;
  }
};

// Phát audio phản hồi
const playResponseAudio = (function () {
  const df = document.createDocumentFragment();
  return function Sound(src) {
    if (!src || src.endsWith("base64,")) return;
    const snd = new Audio(src);
    df.appendChild(snd);
    snd.addEventListener("ended", function () {
      df.removeChild(snd);
    });
    snd.play();
    return snd;
  };
})();

const getRandomID = () => {
  return Date.now().toString(36) + Math.random().toString(36).substr(2);
};

// Cuộn tự động xuống cuối khung Chat
const scrollToBottom = () => {
  const chatWin = $("#chat-window");
  if (chatWin.length) {
    chatWin.animate({ scrollTop: chatWin[0].scrollHeight }, 300);
  }
};

// Thêm tin nhắn Người Dùng vào UI
const populateUserMessage = (userMessage, userRecording) => {
  $("#message-input").val("");

  if (userRecording) {
    const userRepeatButtonID = getRandomID();
    userRepeatButtonIDToRecordingMap[userRepeatButtonID] = userRecording;
    hideUserLoadingAnimation();
    $("#message-list").append(
      `<div class='message-line my-text my-2 text-right'>
        <div class='inline-block bg-purple-700 text-white p-3 rounded-2xl max-w-[80%] text-sm'>
          <div>${userMessage}</div>
        </div>
        <button id='${userRepeatButtonID}' class='repeat-button ml-2 text-purple-400 hover:text-purple-300' onclick='userRepeatButtonIDToRecordingMap[this.id].play()'>
          🔊
        </button>
      </div>`
    );
  } else {
    $("#message-list").append(
      `<div class='message-line my-text my-2 text-right'>
        <div class='inline-block bg-purple-700 text-white p-3 rounded-2xl max-w-[80%] text-sm'>
          <div>${userMessage}</div>
        </div>
      </div>`
    );
  }

  scrollToBottom();
};

// Thêm tin nhắn Bot AI vào UI
const populateBotResponse = async (userMessage) => {
  await showBotLoadingAnimation();
  const response = await processUserMessage(userMessage);
  responses.push(response);

  const repeatButtonID = getRandomID();
  botRepeatButtonIDToIndexMap[repeatButtonID] = responses.length - 1;
  hideBotLoadingAnimation();

  $("#message-list").append(
    `<div class='message-line my-2 text-left flex items-start gap-2'>
      <div class='bg-gray-800 text-gray-100 p-3 rounded-2xl max-w-[80%] text-sm border border-gray-700'>
        ${response.openaiResponseText}
      </div>
      <button id='${repeatButtonID}' class='repeat-button text-purple-400 hover:text-purple-300 mt-2' onclick='playResponseAudio("data:audio/mp3;base64," + responses[botRepeatButtonIDToIndexMap[this.id]].openaiResponseSpeech)'>
        🔊
      </button>
    </div>`
  );

  if (response.openaiResponseSpeech) {
    playResponseAudio("data:audio/mp3;base64," + response.openaiResponseSpeech);
  }

  scrollToBottom();
};

/* ==========================================
   4. KHỞI TẠO EVENT LISTENERS KHI TRANG SẴN SÀNG
   ========================================== */
$(document).ready(function () {
  // 1. Sự kiện gõ bàn phím ô chat
  $("#message-input").keyup(function (event) {
    let inputVal = cleanTextInput($("#message-input").val());

    if (event.keyCode === 13 && inputVal !== "") {
      const message = inputVal;
      populateUserMessage(message, null);
      populateBotResponse(message);
    }
  });

  // 2. Sự kiện bấm nút Micro / Gửi
$("#send-button").click(async function () {
  if (!recording && $("#message-input").val().trim() === "") {
    // Bật ghi âm
    await toggleRecording();
    $(this).removeClass("bg-purple-600").addClass("bg-red-600").html("⏹️");
  } else if (recording) {
    // Tắt ghi âm và xử lý
    $(this).removeClass("bg-red-600").addClass("bg-purple-600").html("🎙️");
    
    const userRecording = await toggleRecording();
    if (userRecording) {
      await showUserLoadingAnimation();
      const userMessage = await getSpeechToText(userRecording);
      populateUserMessage(userMessage, userRecording);
      populateBotResponse(userMessage);
    }
  } else {
    // Gửi tin nhắn bằng văn bản nhập tay
    const message = cleanTextInput($("#message-input").val());
    if (message !== "") {
      populateUserMessage(message, null);
      populateBotResponse(message);
    }
  }
});
  // 3. Chuyển chế độ Dark / Light
  $("#light-dark-mode-switch").change(function () {
    $("body").toggleClass("bg-gray-950 bg-gray-100 text-gray-900 text-gray-100");
    lightMode = !lightMode;
  });

  // 4. Thay đổi Giọng nói
  $("#voice-options").change(function () {
    voiceOption = $(this).val();
  });
});
// 1. Gom toàn bộ tin nhắn chat lại thành văn bản
function getChatTranscript() {
  let transcript = "";
  $("#message-list .message-line").each(function () {
    const text = $(this).text().trim();
    if (text) {
      transcript += text + "\n";
    }
  });
  return transcript;
}

// 2. Gửi request lên API tạo Memo
async function createMemoFromChat() {
  const conversation = getChatTranscript();

  if (!conversation.trim()) {
    alert("Chưa có tin nhắn nào trong khung Chat để tạo Memo!");
    return;
  }

  speakText("Đang tổng hợp thông tin sức khỏe từ cuộc trò chuyện, vui lòng chờ trong giây lát.");

  try {
    const response = await fetch("/api/generate-memo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation: conversation })
    });

    const data = await response.json();

    if (data.success && data.memo) {
      populateMemoModal(data.memo);
      openMemoModal();
      speakText("Đã tạo Memo sức khỏe thành công. Vui lòng kiểm tra lại trước khi lưu.");
    } else {
      alert("Lỗi tạo Memo: " + (data.error || "Không thể xử lý."));
    }
  } catch (err) {
    console.error("Lỗi khi gọi API Memo:", err);
    alert("Không thể kết nối tới máy chủ AI!");
  }
}

// 3. Đổ dữ liệu JSON từ AI vào các ô input trong Modal Review
function populateMemoModal(memo) {
  const today = new Date().toLocaleDateString('vi-VN');

  $("#memo-date").val(memo.date !== "Không đề cập" ? memo.date : today);
  $("#memo-main-concern").val(memo.main_concern || "Không đề cập");
  $("#memo-symptoms").val(memo.symptoms || "Không đề cập");
  $("#memo-timing").val(memo.timing_duration || "Không đề cập");
  $("#memo-severity").val(memo.severity || "Không đề cập");
  $("#memo-medication").val(memo.medication_mentioned || "Không đề cập");
  $("#memo-side-effects").val(memo.side_effects || "Không đề cập");
  $("#memo-what-helped").val(memo.what_helped || "Không đề cập");
  $("#memo-questions").val(memo.questions_for_doctor || "Không đề cập");
}

function openMemoModal() {
  $("#memo-modal").removeClass("hidden");
}

function closeMemoModal() {
  $("#memo-modal").addClass("hidden");
}

// Global handle to persist the folder selection across multiple saves
let memoFolderHandle = null;

async function saveHealthMemo() {
    // 1. Gather form inputs
    const date = document.getElementById("memo-date")?.value.trim() || "Chưa ghi nhận";
    const severity = document.getElementById("memo-severity")?.value.trim() || "Chưa xác định";
    const mainConcern = document.getElementById("memo-main-concern")?.value.trim() || "General";
    const symptoms = document.getElementById("memo-symptoms")?.value.trim() || "Không có";
    const timing = document.getElementById("memo-timing")?.value.trim() || "Không có";
    const medication = document.getElementById("memo-medication")?.value.trim() || "Không có";
    const sideEffects = document.getElementById("memo-side-effects")?.value.trim() || "Không có";
    const whatHelped = document.getElementById("memo-what-helped")?.value.trim() || "Không có";
    const questions = document.getElementById("memo-questions")?.value.trim() || "Không có";

    // 2. Sanitize date and topic
    const safeDate = date.replace(/[/\\?%*:|"<> ]/g, '-');
    const safeConcern = mainConcern.replace(/[^a-zA-Z0-9]/g, '_').substring(0, 20).replace(/^_+|_+$/g, '') || "General";

    // 3. Increment counter per date
    const storageKey = `memo_count_${safeDate}`;
    let count = parseInt(localStorage.getItem(storageKey) || "0", 10) + 1;
    localStorage.setItem(storageKey, count.toString());

    const filename = `Memo_${safeDate}_(${count})_${safeConcern}.txt`;

    // 4. Format memo text content
    const textContent = 
`==================================================
           NHẬT KÝ SỨC KHỎE (HEALTH MEMO)
==================================================
📅 Ngày ghi nhận: ${date}
🚨 Mức độ nghiêm trọng: ${severity}

🎯 VẤN ĐỀ CHÍNH (MAIN CONCERN):
${mainConcern}

🤒 TRIỆU CHỨNG XUẤT HIỆN (SYMPTOMS):
${symptoms}

⏱️ THỜI ĐIỂM & KÉO DÀI:
${timing}

💊 THUỐC LIÊN QUAN:
${medication}

⚠️ TÁC DỤNG PHỤ (NGHI NGỜ):
${sideEffects}

🧘 MẸO / VIỆC ĐÃ LÀM ĐỂ ĐỞ ĐAU:
${whatHelped}

❓ CÂU HỎI CẦN HỎI BÁC SĨ (QUESTIONS FOR DOCTOR):
${questions}

--------------------------------------------------
⚠️ CẢNH BÁO: Memo này chỉ ghi nhận thông tin bệnh nhân
trình bày, KHÔNG PHẢI LÀ CHẨN ĐOÁN Y KHOA.
==================================================`;

    // 5. Create or save into dedicated "PillGuard_Memos" folder
    if ('showDirectoryPicker' in window) {
        try {
            if (!memoFolderHandle) {
                // User picks base directory (Downloads) on first download
                const baseDir = await window.showDirectoryPicker({ mode: 'readwrite' });
                // Automatically creates or reuses subfolder 'PillGuard_Memos'
                memoFolderHandle = await baseDir.getDirectoryHandle('PillGuard_Memos', { create: true });
            }

            // Write text file directly into PillGuard_Memos
            const fileHandle = await memoFolderHandle.getFileHandle(filename, { create: true });
            const writable = await fileHandle.createWritable();
            await writable.write(textContent);
            await writable.close();

            alert(`✅ Đã lưu vào thư mục: PillGuard_Memos/${filename}`);
            if (typeof closeMemoModal === "function") closeMemoModal();
            return;
        } catch (err) {
            console.warn("Folder permission cancelled/failed, using standard download.", err);
            memoFolderHandle = null;
        }
    }

    // Fallback: Standard browser download if browser doesn't support directory handles
    const blob = new Blob([textContent], { type: "text/plain;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);

    if (typeof closeMemoModal === "function") closeMemoModal();
}
function parseAndFillMemoForm(rawText) {
    // 1. Chuẩn hóa ký tự xuống dòng để tránh lỗi trên Windows
    const text = rawText.replace(/\r\n/g, '\n');

    // Hàm hỗ trợ lấy nội dung giữa tiêu đề hiện tại và tiêu đề tiếp theo
    const getFieldValue = (headerRegex, stopRegex) => {
        const regex = new RegExp(`${headerRegex}\\s*\\n([\\s\\S]*?)(?=\\n+(?:${stopRegex})|\\n---+|$)`, 'i');
        const match = text.match(regex);
        return match && match[1] ? match[1].trim() : '';
    };

    // 2. Trích xuất từng trường dữ liệu
    const date = (text.match(/📅 Ngày ghi nhận:\s*(.*)/) || [])[1] || '';
    const severity = (text.match(/🚨 Mức độ nghiêm trọng:\s*(.*)/) || [])[1] || '';

    const mainConcern = getFieldValue('🎯 VẤN ĐỀ CHÍNH \\(MAIN CONCERN\\):', '🤒|⏱️|💊|⚠️|🧘|❓');
    const symptoms = getFieldValue('🤒 TRIỆU CHỨNG XUẤT HIỆN \\(SYMPTOMS\\):', '⏱️|💊|⚠️|🧘|❓');
    const timing = getFieldValue('⏱️ THỜI ĐIỂM & KÉO DÀI:', '💊|⚠️|🧘|❓');
    const medication = getFieldValue('💊 THUỐC LIÊN QUAN:', '⚠️|🧘|❓');
    const sideEffects = getFieldValue('⚠️ TÁC DỤNG PHỤ \\(NGHI NGỜ\\):', '🧘|❓');
    const whatHelped = getFieldValue('🧘 MẸO \\/ VIỆC ĐÃ LÀM ĐỂ ĐỞ ĐAU:', '❓');
    const questions = getFieldValue('❓ CÂU HỎI CẦN HỎI BÁC SĨ \\(QUESTIONS FOR DOCTOR\\):', '---|===');

    // 3. Đổ dữ liệu vào các ô input trên giao diện modal
    if (document.getElementById("memo-date")) document.getElementById("memo-date").value = date.trim();
    if (document.getElementById("memo-severity")) document.getElementById("memo-severity").value = severity.trim();
    if (document.getElementById("memo-main-concern")) document.getElementById("memo-main-concern").value = mainConcern;
    if (document.getElementById("memo-symptoms")) document.getElementById("memo-symptoms").value = symptoms;
    if (document.getElementById("memo-timing")) document.getElementById("memo-timing").value = timing;
    if (document.getElementById("memo-medication")) document.getElementById("memo-medication").value = medication;
    if (document.getElementById("memo-side-effects")) document.getElementById("memo-side-effects").value = sideEffects;
    if (document.getElementById("memo-what-helped")) document.getElementById("memo-what-helped").value = whatHelped;
    if (document.getElementById("memo-questions")) document.getElementById("memo-questions").value = questions;
}

// Cập nhật lại hàm loadMemoFromFile để gọi hàm bóc tách mới này
function loadMemoFromFile(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
        parseAndFillMemoForm(e.target.result);

        // Mở Modal giao diện Memo
        const memoModal = document.getElementById('memo-modal');
        if (memoModal) memoModal.classList.remove('hidden');

        event.target.value = ''; // Reset input file
    };

    reader.readAsText(file, "UTF-8");
}

// Hàm hỗ trợ mở Modal Memo (nếu chưa có)
function openMemoModal() {
    const memoModal = document.getElementById('memo-modal');
    if (memoModal) memoModal.classList.remove('hidden');
}

function closeMemoModal() {
    const memoModal = document.getElementById('memo-modal');
    if (memoModal) memoModal.classList.add('hidden');
}
// Run automatically when the page loads
document.addEventListener('DOMContentLoaded', fetchSavedMemos);

async function fetchSavedMemos() {
    const response = await fetch('/api/list-memos');
    const data = await response.json();
    
    const dropdown = document.getElementById('memo-select-dropdown');
    if (!dropdown || !data.files) return;

    dropdown.innerHTML = '<option value="">-- Choose a Memo --</option>';
    data.files.forEach(filename => {
        const option = document.createElement('option');
        option.value = filename;
        option.textContent = filename;
        dropdown.appendChild(option);
    });
}

async function loadSelectedMemo(filename) {
    if (!filename) return;
    const res = await fetch(`/api/get-memo/${filename}`);
    const text = await res.text();
    
    // Pass the retrieved text to your parser
    parseAndFillMemoForm(text); 
}
async function handleMemoSearch(searchTerm) {
    try {
        const response = await fetch(`/api/search-memos?q=${encodeURIComponent(searchTerm)}`);
        const data = await response.json();

        if (data.success) {
            renderSearchResults(data.results);
        }
    } catch (err) {
        console.error("Search error:", err);
    }
}

function renderSearchResults(memos) {
    const listContainer = document.getElementById("search-results-list");
    if (!listContainer) return;

    listContainer.innerHTML = "";

    if (memos.length === 0) {
        listContainer.innerHTML = "<p class='text-gray-400'>No matching memos found.</p>";
        return;
    }

    memos.forEach(memo => {
        const item = document.createElement("button");
        item.className = "w-full text-left p-2 bg-gray-800 hover:bg-gray-700 rounded mb-2 text-white block";
        item.textContent = memo.filename;
        
        // When clicked, parse the content and open it directly in the UI modal
        item.onclick = () => {
            parseAndFillMemoForm(memo.content);
            document.getElementById('memo-modal')?.classList.remove('hidden');
        };

        listContainer.appendChild(item);
    });
}

// Replace with your Google Cloud OAuth Client ID
const GOOGLE_CLIENT_ID = '299054550160-lg50bdpaab1k4ch0ptpot7pl5eg4m14g.apps.googleusercontent.com';

function uploadAllToGoogleCalendar() {
  if (typeof google === 'undefined') {
    alert("Thư viện Google chưa sẵn sàng, vui lòng thử lại sau vài giây.");
    return;
  }

  const rows = document.querySelectorAll('#history-table-body tr');
  if (!rows || rows.length === 0) {
    alert("Chưa có lịch uống thuốc để tải lên!");
    return;
  }

  // Request OAuth permission & trigger single-click upload
  const tokenClient = google.accounts.oauth2.initTokenClient({
    client_id: GOOGLE_CLIENT_ID,
    scope: 'https://www.googleapis.com/auth/calendar.events',
    callback: async (tokenResponse) => {
      if (tokenResponse.access_token) {
        await processAndUploadEvents(tokenResponse.access_token);
      }
    },
  });

  tokenClient.requestAccessToken();
}

async function processAndUploadEvents(accessToken) {
  const rows = document.querySelectorAll('#history-table-body tr');
  const timeSlots = {
    'Sáng': '06:00',
    'Trưa': '12:00',
    'Chiều': '15:00',
    'Tối': '20:00'
  };

  const today = new Date().toISOString().split('T')[0];
  let schedule = { 'Sáng': [], 'Trưa': [], 'Chiều': [], 'Tối': [] };

  rows.forEach((row) => {
    const cols = row.querySelectorAll('td');
    if (cols.length >= 4) {
      const medName = cols[1].innerText.trim();
      const rawTimes = cols[2].innerText.trim();
      const notes = cols[3].innerText.trim();

      Object.keys(timeSlots).forEach((slot) => {
        if (rawTimes.includes(slot)) {
          schedule[slot].push({ name: medName, note: notes });
        }
      });
    }
  });

  let uploadPromises = [];

  for (const [slot, timeStr] of Object.entries(timeSlots)) {
    if (schedule[slot].length > 0) {
      const medList = schedule[slot].map(item => `• ${item.name}${item.note ? ' (' + item.note + ')' : ''}`).join('\n');

      const eventData = {
        summary: `💊 Uống Thuốc Buổi ${slot}`,
        description: `📋 DANH SÁCH THUỐC:\n${medList}\n\n--- PillGuard AI`,
        start: { dateTime: `${today}T${timeStr}:00+07:00`, timeZone: 'Asia/Ho_Chi_Minh' },
        end: { dateTime: `${today}T${timeStr}:30+07:00`, timeZone: 'Asia/Ho_Chi_Minh' },
        reminders: {
          useDefault: false,
          overrides: [{ method: 'popup', minutes: 10 }] // 10-min notification alert
        }
      };

      uploadPromises.push(
        fetch('https://www.googleapis.com/calendar/v3/calendars/primary/events', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(eventData)
        })
      );
    }
  }

  try {
    await Promise.all(uploadPromises);
    alert("✅ Đã tự động tải toàn bộ lịch uống thuốc vào Google Calendar của bạn!");
  } catch (err) {
    console.error(err);
    alert("Có lỗi xảy ra khi đồng bộ lịch lên Google Calendar!");
  }
}
