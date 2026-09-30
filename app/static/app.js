const fileInput = document.querySelector("#fileInput");
const dropZone = document.querySelector("#dropZone");
const fileCount = document.querySelector("#fileCount");
const scanState = document.querySelector("#scanState");
const summary = document.querySelector("#summary");
const fileList = document.querySelector("#fileList");
const generateBtn = document.querySelector("#generateBtn");
const buttonHint = document.querySelector("#buttonHint");
const message = document.querySelector("#message");
const qrPreview = document.querySelector("#qrPreview");
const qrPlaceholder = document.querySelector("#qrPlaceholder");
const codePreview = document.querySelector("#codePreview");
const phonePreview = document.querySelector("#phonePreview");
const rescuePhone = document.querySelector("#rescuePhone");
const sortCodes = document.querySelector("#sortCodes");
const previewSize = document.querySelector("#previewSize");
const labelPreview = document.querySelector("#labelPreview");
const clearFiles = document.querySelector("#clearFiles");

let selectedFiles = [];
let inspection = null;

const sizeLabels = { mini: "60 × 90 mm", standard: "80 × 120 mm", large: "100 × 150 mm" };
const layoutLabels = { left: "左竖排", right: "右竖排" };

function selectedSize() {
  return document.querySelector('input[name="size"]:checked').value;
}

function selectedLayout() {
  return document.querySelector('input[name="layout"]:checked').value;
}

function setMessage(text = "", kind = "") {
  message.textContent = text;
  message.className = `message ${kind}`.trim();
}

function updatePreview() {
  const size = selectedSize();
  const layout = selectedLayout();
  previewSize.textContent = `${sizeLabels[size]} · ${layoutLabels[layout]}`;
  labelPreview.classList.toggle("layout-right", layout === "right");
  labelPreview.style.transform = size === "mini" ? "scale(.9)" : size === "large" ? "scale(1.04)" : "scale(1)";
  phonePreview.textContent = rescuePhone.value.trim() ? `救援电话:${rescuePhone.value.trim()}` : "";
}

async function addFiles(incoming) {
  const candidates = [...incoming];
  const images = candidates.filter((file) => file.type.startsWith("image/") && file.size <= 10 * 1024 * 1024);
  const rejected = candidates.length - images.length;
  const existing = new Set(selectedFiles.map((file) => `${file.name}|${file.size}|${file.lastModified}`));
  let limitExceeded = false;
  for (const file of images) {
    const key = `${file.name}|${file.size}|${file.lastModified}`;
    if (!existing.has(key)) {
      if (selectedFiles.length >= 200) {
        limitExceeded = true;
        continue;
      }
      selectedFiles.push(file);
      existing.add(key);
    }
  }
  await inspectFiles();
  if (rejected) setMessage(`已忽略 ${rejected} 个非图片或超过10MB的文件。`, "error");
  if (limitExceeded) setMessage("单次最多处理200张图片，超出部分未加入。", "error");
}

async function inspectFiles() {
  inspection = null;
  generateBtn.disabled = true;
  setMessage();
  fileCount.textContent = selectedFiles.length ? `已选择 ${selectedFiles.length} 张` : "尚未选择图片";
  clearFiles.hidden = selectedFiles.length === 0;
  if (!selectedFiles.length) {
    fileList.innerHTML = "";
    summary.hidden = true;
    scanState.hidden = true;
    codePreview.textContent = "安全码号";
    qrPreview.removeAttribute("src");
    qrPreview.hidden = true;
    qrPlaceholder.hidden = false;
    buttonHint.textContent = "请先上传有效二维码";
    return;
  }

  scanState.hidden = false;
  summary.hidden = true;
  fileList.innerHTML = "";
  const form = new FormData();
  selectedFiles.forEach((file) => form.append("files", file));

  try {
    const response = await fetch("api/inspect", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "识别失败");
    inspection = payload;
    renderInspection(payload);
  } catch (error) {
    setMessage(error.message || "二维码识别失败", "error");
  } finally {
    scanState.hidden = true;
  }
}

function renderInspection(payload) {
  const { total, valid, duplicates, invalid } = payload.summary;
  summary.hidden = false;
  document.querySelector("#sumTotal").textContent = total;
  document.querySelector("#sumValid").textContent = valid;
  document.querySelector("#sumDuplicate").textContent = duplicates;
  document.querySelector("#sumInvalid").textContent = invalid;

  fileList.innerHTML = payload.items.map((item, index) => {
    const statusText = item.status === "ok" ? "有效" : item.status === "duplicate" ? "重复" : "异常";
    const code = item.formatted_code || item.error || "未提取";
    return `<div class="file-row">
      <span class="file-name" title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</span>
      <span class="file-code" title="${escapeHtml(item.error || "")}">${escapeHtml(code)}</span>
      <span class="status ${item.status}">${statusText}</span>
      <button class="remove-file" type="button" data-index="${index}" aria-label="移除 ${escapeHtml(item.filename)}">×</button>
    </div>`;
  }).join("");

  const firstValidIndex = payload.items.findIndex((item) => item.status === "ok");
  if (firstValidIndex >= 0) {
    qrPreview.src = payload.preview_image;
    qrPreview.hidden = false;
    qrPlaceholder.hidden = true;
    codePreview.textContent = payload.items[firstValidIndex].formatted_code;
  }

  const ready = total > 0 && valid === total && duplicates === 0 && invalid === 0;
  generateBtn.disabled = !ready;
  buttonHint.textContent = ready ? `共 ${total} 页` : "请处理重复或异常图片";
  if (!ready) setMessage("请移除重复或无法识别的图片后再生成。", "error");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

async function generatePdf() {
  if (!inspection || generateBtn.disabled) return;
  generateBtn.disabled = true;
  generateBtn.querySelector("span").textContent = "正在生成PDF…";
  buttonHint.textContent = "请稍候";
  setMessage("正在制作标识牌并校验页面尺寸…");

  const form = new FormData();
  selectedFiles.forEach((file) => form.append("files", file));
  form.append("size_key", selectedSize());
  form.append("layout_key", selectedLayout());
  form.append("rescue_phone", rescuePhone.value.trim());
  form.append("sort_codes", String(sortCodes.checked));

  try {
    const response = await fetch("api/generate", { method: "POST", body: form });
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.detail || "PDF生成失败");
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    const filename = match ? decodeURIComponent(match[1]) : "特种设备安全码.pdf";
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
    setMessage(`已生成 ${inspection.summary.total} 页PDF。`, "success");
  } catch (error) {
    setMessage(error.message || "PDF生成失败", "error");
  } finally {
    generateBtn.querySelector("span").textContent = "生成并下载PDF";
    generateBtn.disabled = false;
    buttonHint.textContent = `共 ${inspection.summary.total} 页`;
  }
}

fileInput.addEventListener("change", () => {
  addFiles(fileInput.files);
  fileInput.value = "";
});
dropZone.addEventListener("dragover", (event) => { event.preventDefault(); dropZone.classList.add("is-dragging"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("is-dragging"));
dropZone.addEventListener("drop", (event) => { event.preventDefault(); dropZone.classList.remove("is-dragging"); addFiles(event.dataTransfer.files); });
fileList.addEventListener("click", (event) => {
  const button = event.target.closest(".remove-file");
  if (!button) return;
  selectedFiles.splice(Number(button.dataset.index), 1);
  inspectFiles();
});
document.querySelectorAll('input[name="size"]').forEach((input) => input.addEventListener("change", updatePreview));
document.querySelectorAll('input[name="layout"]').forEach((input) => input.addEventListener("change", updatePreview));
rescuePhone.addEventListener("input", updatePreview);
generateBtn.addEventListener("click", generatePdf);
clearFiles.addEventListener("click", () => {
  selectedFiles = [];
  inspectFiles();
});
document.addEventListener("paste", (event) => {
  const images = [...(event.clipboardData?.files || [])].filter((file) => file.type.startsWith("image/"));
  if (images.length) addFiles(images);
});
updatePreview();

if (document.modelContext?.registerTool) {
  const lifecycle = new AbortController();
  Promise.resolve(document.modelContext.registerTool({
    name: "get_safety_code_generator_state",
    title: "读取安全码生成器状态",
    description: "读取当前上传数量、识别结果和输出设置，不会修改页面。",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, untrustedContentHint: false },
    execute() {
      return {
        files: selectedFiles.length,
        summary: inspection?.summary || null,
        size: selectedSize(),
        layout: selectedLayout(),
        rescuePhoneEnabled: Boolean(rescuePhone.value.trim()),
        sortCodes: sortCodes.checked,
      };
    },
  }, { signal: lifecycle.signal })).catch(() => {});

  Promise.resolve(document.modelContext.registerTool({
    name: "set_safety_code_output_options",
    title: "设置安全码输出选项",
    description: "设置标识牌尺寸、救援电话和排序方式，并同步更新页面预览。",
    inputSchema: {
      type: "object",
      properties: {
        size: { type: "string", enum: ["mini", "standard", "large"] },
        layout: { type: "string", enum: ["left", "right"] },
        rescuePhone: { type: "string", maxLength: 20 },
        sortCodes: { type: "boolean" },
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, untrustedContentHint: false },
    execute(input) {
      if (input.size) document.querySelector(`input[name="size"][value="${input.size}"]`).checked = true;
      if (input.layout) document.querySelector(`input[name="layout"][value="${input.layout}"]`).checked = true;
      if (typeof input.rescuePhone === "string") rescuePhone.value = input.rescuePhone;
      if (typeof input.sortCodes === "boolean") sortCodes.checked = input.sortCodes;
      updatePreview();
      return { size: selectedSize(), layout: selectedLayout(), rescuePhone: rescuePhone.value, sortCodes: sortCodes.checked };
    },
  }, { signal: lifecycle.signal })).catch(() => {});
}
