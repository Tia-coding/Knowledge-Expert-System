guard("admin");

const state = {
  documents: [],
  selectedFiles: [],
};

/* =========================================================
   ELEMENTS
========================================================= */

const uploadZone =
  document.querySelector("#uploadZone");

const fileInput =
  document.querySelector("#fileInput");

const uploadBtn =
  document.querySelector("#uploadBtn");

const selectedFilesContainer =
  document.querySelector("#selectedFiles");

const uploadProgress =
  document.querySelector("#uploadProgress span");

const fileSearch =
  document.querySelector("#fileSearch");

const clearLogsBtn =
  document.querySelector("#clearLogsBtn");

/* =========================================================
   SCROLL NAVIGATION & SCROLL SPY
========================================================= */

const ADMIN_SECTIONS = [
  "dashboard",
  "upload",
  "manage",
  "knowledge",
  "logs",
];

let scrollSpyObserver = null;

function setActiveNav(sectionId) {
  document.querySelectorAll(".nav-item[data-section]").forEach(nav => {
    nav.classList.toggle("active", nav.dataset.section === sectionId);
  });
}

function refreshSectionData(sectionId) {
  if (sectionId === "manage") {
    loadDocuments().catch(e => console.error(e));
  } else if (sectionId === "logs") {
    loadLogs().catch(e => console.error(e));
  } else if (sectionId === "dashboard") {
    loadMetrics().catch(e => console.error(e));
  }
}

function scrollToSection(sectionId) {
  const target = document.getElementById(sectionId);
  if (!target) {
    return;
  }

  target.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });

  setActiveNav(sectionId);
  refreshSectionData(sectionId);
}

function initScrollSpy() {
  const sections = ADMIN_SECTIONS
    .map(id => document.getElementById(id))
    .filter(Boolean);

  if (!sections.length) {
    return;
  }

  if (scrollSpyObserver) {
    scrollSpyObserver.disconnect();
  }

  const visibility = new Map(
    ADMIN_SECTIONS.map(id => [id, 0])
  );

  scrollSpyObserver = new IntersectionObserver(
    entries => {
      entries.forEach(entry => {
        visibility.set(
          entry.target.id,
          entry.isIntersecting ? entry.intersectionRatio : 0
        );
      });

      let activeId = ADMIN_SECTIONS[0];
      let bestRatio = -1;

      ADMIN_SECTIONS.forEach(id => {
        const ratio = visibility.get(id) || 0;
        if (ratio > bestRatio) {
          bestRatio = ratio;
          activeId = id;
        }
      });

      if (bestRatio > 0) {
        setActiveNav(activeId);
      }
    },
    {
      root: null,
      rootMargin: "-12% 0px -55% 0px",
      threshold: [0, 0.15, 0.35, 0.55, 0.75, 1],
    }
  );

  sections.forEach(section => {
    scrollSpyObserver.observe(section);
  });
}

document.addEventListener("click", (event) => {
  const navItem = event.target.closest(".nav-item[data-section]");
  const logoutItem = event.target.closest("[data-logout]");

  if (navItem) {
    event.preventDefault();
    scrollToSection(navItem.dataset.section);
  }

  if (logoutItem) {
    event.preventDefault();
    logout();
  }
});

/* =========================================================
   HELPERS
========================================================= */

function escapeHtml(value) {

  return String(value || "")

    .replaceAll("&", "&amp;")

    .replaceAll("<", "&lt;")

    .replaceAll(">", "&gt;")

    .replaceAll('"', "&quot;")

    .replaceAll("'", "&#039;");

}

function formatSize(bytes) {

  if (!bytes) {
    return "0 KB";
  }

  return bytes < 1024 * 1024

    ? `${(bytes / 1024).toFixed(2)} KB`

    : `${(bytes / 1024 / 1024).toFixed(2)} MB`;

}

function formatDate(dateString) {

  if (!dateString) {
    return "-";
  }

  try {

    return new Date(
      dateString
    ).toLocaleString("en-IN", {

      dateStyle: "medium",

      timeStyle: "short"

    });

  } catch {

    return "-";

  }

}

function userStatus(status) {

  if (status === "Indexed") {
    return "Processed";
  }

  return status || "Uploaded";

}

function indexingStatus(status) {

  if (status === "Indexed") {

    return `
      <span class="status success">
        Indexed
      </span>
    `;

  }

  if (status === "Processing") {

    return `
      <span class="status warning">
        Processing
      </span>
    `;

  }

  if (status === "Failed") {

    return `
      <span class="status danger">
        Failed
      </span>
    `;

  }

  return `
    <span class="status neutral">
      Uploaded
    </span>
  `;

}

/* =========================================================
   FILE SELECTION
========================================================= */

function resetFileInput() {
  if (fileInput) {
    fileInput.value = "";
  }
}

function fileSelectionKey(file) {
  return `${file.name}|${file.size}|${file.lastModified}`;
}

function mergeSelectedFiles(existing, incoming) {
  const seen = new Set(existing.map(fileSelectionKey));
  const merged = [...existing];

  incoming.forEach(file => {
    const key = fileSelectionKey(file);
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(file);
    }
  });

  return merged;
}

if (uploadZone && fileInput) {

  uploadZone.addEventListener(
    "click",
    () => fileInput.click()
  );

}

if (fileInput) {

  fileInput.addEventListener(
    "change",
    event => {

      const picked = Array.from(event.target.files || []);

      if (picked.length) {
        state.selectedFiles = mergeSelectedFiles(
          state.selectedFiles,
          picked
        );
      }

      resetFileInput();
      renderSelectedFiles();

    }
  );

}

function renderSelectedFiles() {

  if (!selectedFilesContainer) {
    return;
  }

  if (!state.selectedFiles.length) {

    selectedFilesContainer.innerHTML = `
      <div class="empty-selected-files">
        No files selected
      </div>
    `;

    return;

  }

  selectedFilesContainer.innerHTML = `

    <div class="selected-files-container">

      ${state.selectedFiles.map((file, index) => `

        <div class="selected-file-card">

          <button
            type="button"
            class="remove-selected-file"
            data-index="${index}"
          >
            &times;
          </button>

          <div class="selected-file-top">

            <div class="selected-file-badge">
              ${getFileType(file.name)}
            </div>

          </div>

          <div class="selected-file-name">
            ${escapeHtml(file.name)}
          </div>

          <div class="selected-file-meta">
            ${formatSize(file.size)}
          </div>

        </div>

      `).join("")}

    </div>

  `;

  document.querySelectorAll(
    ".remove-selected-file"
  ).forEach(button => {

    button.addEventListener(
      "click",
      event => {

        event.preventDefault();

        event.stopPropagation();

        removeSelectedFile(
          Number(button.dataset.index)
        );

      }
    );

  });

}

function removeSelectedFile(index) {

  state.selectedFiles.splice(
    index,
    1
  );

  resetFileInput();
  renderSelectedFiles();

}

function clearSelectedFiles() {

  state.selectedFiles = [];
  resetFileInput();
  renderSelectedFiles();

}

function getFileType(filename = "") {

  const lower =
    filename.toLowerCase();

  if (lower.endsWith(".pdf")) {
    return "PDF";
  }

  if (
    lower.endsWith(".doc") ||
    lower.endsWith(".docx")
  ) {
    return "DOC";
  }

  if (
    lower.endsWith(".txt") ||
    lower.endsWith(".md")
  ) {
    return "TEXT";
  }

  return "FILE";

}

/* =========================================================
   UPLOAD
========================================================= */

if (uploadBtn) {

  uploadBtn.addEventListener(
    "click",
    async () => {

      if (!state.selectedFiles.length) {

        toast(
          "Please select files first"
        );

        return;

      }

      try {

        const formData =
          new FormData();

        state.selectedFiles.forEach(file => {

          formData.append(
            "files",
            file
          );

        });

        const response = await fetch(
          "/api/upload",
          {
            method: "POST",
            headers: authHeaders(),
            body: formData,
          }
        );

        if (!response.ok) {
          const error = await response.json().catch(() => ({ detail: "Upload failed" }));
          throw new Error(error.detail || "Upload failed");
        }

        toast("Documents uploaded successfully");

        clearSelectedFiles();

        await loadDocuments().catch(e => console.error(e));

        await loadMetrics().catch(e => console.error(e));

      } catch (error) {
        console.error(error);
        toast(error.message || "Upload failed");
      }

    }
  );

}

/* =========================================================
   DOCUMENTS
========================================================= */

async function loadDocuments() {
  try {
    const docs = await api("/documents");
    state.documents = Array.isArray(docs) ? docs : [];
    renderDocuments(state.documents);
  } catch (error) {
    console.error("Failed to load documents data:", error);
    state.documents = [];
    renderDocuments([]);
  }
}

function renderDocuments(rows) {

  const tbody =
    document.querySelector(
      "#documentsTable tbody"
    );

  if (!tbody) {
    return;
  }

  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;" class="muted">No documents found.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(doc => `

    <tr>

      <td>${doc.id || "-"}</td>

      <td>${escapeHtml(doc.filename)}</td>

      <td>${escapeHtml(doc.document_type || "Unknown")}</td>

      <td>${formatSize(doc.size_bytes)}</td>

      <td>${formatDate(doc.created_at)}</td>

      <td>${userStatus(doc.status)}</td>

      <td>${indexingStatus(doc.status)}</td>

      <td>

        <div class="action-group">

          <button
            type="button"
            class="btn-primary"
            data-action="open"
            data-id="${doc.id}"
          >
            Open
          </button>

          <button
            type="button"
            class="btn-light"
            data-action="download"
            data-id="${doc.id}"
          >
            Download
          </button>

          <button
            type="button"
            class="btn-danger"
            data-action="delete"
            data-id="${doc.id}"
          >
            Delete
          </button>

        </div>

      </td>

    </tr>

  `).join("");

}

/* =========================================================
   DOCUMENT ACTIONS (delegated — avoids broken inline handlers)
========================================================= */

function parseFilenameFromDisposition(disposition) {
  if (!disposition) {
    return null;
  }

  const utfMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utfMatch?.[1]) {
    try {
      return decodeURIComponent(utfMatch[1].trim());
    } catch {
      return utfMatch[1].trim();
    }
  }

  const quotedMatch = disposition.match(/filename="([^"]+)"/i);
  if (quotedMatch?.[1]) {
    return quotedMatch[1];
  }

  const plainMatch = disposition.match(/filename=([^;]+)/i);
  if (plainMatch?.[1]) {
    return plainMatch[1].trim();
  }

  return null;
}

async function fetchDocumentBlob(id, download = false) {
  const url = download
    ? `/api/download/${id}?download=true`
    : `/api/download/${id}`;

  const response = await fetch(url, { headers: authHeaders() });

  if (response.status === 401 || response.status === 403) {
    clearAuthSession();
    location.href = "/index.html";
    return null;
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || "Request failed");
  }

  const blob = await response.blob();
  const filename =
    parseFilenameFromDisposition(
      response.headers.get("Content-Disposition")
    ) || "document";

  return { blob, filename };
}

async function openDoc(id) {
  try {
    const result = await fetchDocumentBlob(id, false);
    if (!result) {
      return;
    }

    const blobUrl = URL.createObjectURL(result.blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.target = "_blank";
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
  } catch (e) {
    console.error(e);
    toast(e.message || "Could not open document");
  }
}

async function downloadDoc(id) {
  try {
    const doc = state.documents.find(d => d.id === id);
    const result = await fetchDocumentBlob(id, true);
    if (!result) {
      return;
    }

    const filename = result.filename || doc?.filename || "document";
    const blobUrl = URL.createObjectURL(result.blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(blobUrl);
    toast("Download started");
  } catch (e) {
    console.error(e);
    toast(e.message || "Download failed");
  }
}

async function deleteDoc(id) {
  const confirmed = confirm("Delete this document?");
  if (!confirmed) {
    return;
  }

  try {
    await api(`/documents/${id}`, { method: "DELETE" });
    toast("Document deleted");
    await loadDocuments().catch(() => {});
    await loadMetrics().catch(() => {});
  } catch (e) {
    console.error(e);
    toast(e.message || "Failed to delete document");
  }
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("#documentsTable [data-action]");
  if (!button) {
    return;
  }

  event.preventDefault();

  const id = Number(button.dataset.id);
  const action = button.dataset.action;

  if (!id) {
    return;
  }

  if (action === "open") {
    openDoc(id);
  } else if (action === "download") {
    downloadDoc(id);
  } else if (action === "delete") {
    deleteDoc(id);
  }
});

/* =========================================================
   SEARCH
========================================================= */

if (fileSearch) {

  fileSearch.addEventListener(
    "input",
    event => {

      const value =
        event.target.value
          .toLowerCase();

      const filtered =
        state.documents.filter(
          doc =>
            (doc.filename || "")
              .toLowerCase()
              .includes(value)
        );

      renderDocuments(
        filtered
      );

    }
  );

}

/* =========================================================
   METRICS
========================================================= */

async function loadMetrics() {
  const targetMetric = document.querySelector("#totalDocuments");
  if (!targetMetric) return;

  try {
    const metrics = await api("/metrics");
    targetMetric.textContent = metrics.total_documents !== undefined ? metrics.total_documents : 0;
  } catch (error) {
    console.error("Failed to load backend metrics counters:", error);
    targetMetric.textContent = "0";
  }
}

/* =========================================================
   LOGS
========================================================= */

async function loadLogs() {
  const tbody = document.querySelector("#logsTable tbody");
  if (!tbody) return;

  try {
    const logs = await api("/security-logs");
    const logArray = Array.isArray(logs) ? logs : [];

    if (logArray.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;" class="muted">No security logs logged.</td></tr>`;
      return;
    }

    tbody.innerHTML = logArray.map(log => `
      <tr>
        <td>${escapeHtml(log.action)}</td>
        <td>${escapeHtml(log.username)}</td>
        <td>${escapeHtml(log.ip_address)}</td>
        <td>${formatDate(log.created_at)}</td>
      </tr>
    `).join("");
  } catch (error) {
    console.error("Failed to load security logs:", error);
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;" class="status danger-text">Error loading logs.</td></tr>`;
  }
}

/* =========================================================
   INITIAL LOAD
========================================================= */

if (clearLogsBtn) {
  clearLogsBtn.addEventListener("click", async () => {
    if (!confirm("Clear all security logs?")) {
      return;
    }

    try {
      await api("/security-logs", { method: "DELETE" });
      toast("Security logs cleared");
      await loadLogs();
    } catch (error) {
      console.error(error);
      toast(error.message || "Failed to clear logs");
    }
  });
}

window.addEventListener("DOMContentLoaded", () => {
  renderSelectedFiles();
  initScrollSpy();
  setActiveNav("dashboard");

  loadMetrics().catch(e => console.error("Initial metrics fetch failed:", e));
  loadDocuments().catch(e => console.error("Initial documents fetch failed:", e));
  loadLogs().catch(e => console.error("Initial security logs fetch failed:", e));
});