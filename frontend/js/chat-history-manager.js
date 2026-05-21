/**
 * ChatGPT-style conversation manager for the user dashboard.
 */

class ChatHistoryManager {
  constructor() {
    this.currentConversationId = null;
    this.conversations = [];
    this.messages = [];
    this.searchQuery = "";
    this.activeStorageKey = "nrsc_active_conversation_id";
  }

  async init() {
    await this.loadConversations();

    const savedId = localStorage.getItem(this.activeStorageKey);
    const savedExists = savedId && this.conversations.some(
      c => c.conversation_id === savedId
    );

    if (savedExists) {
      await this.openConversation(savedId, { persist: false });
      return;
    }

    if (this.conversations.length) {
      await this.openConversation(
        this.conversations[0].conversation_id,
        { persist: false }
      );
      return;
    }

    this.startNewConversation();
  }

  startNewConversation() {
    this.currentConversationId = null;
    this.messages = [];
    localStorage.removeItem(this.activeStorageKey);
    this.renderConversationList();
    this.renderMessages();
    this.updateChatHeader();
    this.clearSourcesPanel();
    this.scrollMessagesToBottom();
  }

  async loadConversations() {
    try {
      const rows = await api("/history/conversations");
      this.conversations = Array.isArray(rows) ? rows : [];
    } catch (error) {
      console.error("Failed to load conversations:", error);
      this.conversations = [];
    }
  }

  setSearchQuery(query) {
    this.searchQuery = (query || "").trim().toLowerCase();
    this.renderConversationList();
  }

  getFilteredConversations() {
    if (!this.searchQuery) {
      return this.conversations;
    }

    return this.conversations.filter(thread =>
      (thread.title || "").toLowerCase().includes(this.searchQuery)
    );
  }

  async openConversation(conversationId, options = {}) {
    const { persist = true } = options;

    if (!conversationId) {
      this.startNewConversation();
      return;
    }

    try {
      const rows = await api(
        `/history?conversation_id=${encodeURIComponent(conversationId)}`
      );

      this.currentConversationId = conversationId;
      this.messages = Array.isArray(rows) ? rows : [];

      if (persist) {
        localStorage.setItem(this.activeStorageKey, conversationId);
      }

      this.renderConversationList();
      this.renderMessages();
      this.updateChatHeader();
      this.showLatestSources();
      this.scrollMessagesToBottom();
      setActive("ask");
    } catch (error) {
      console.error("Failed to open conversation:", error);
      toast("Error loading conversation: " + error.message);
    }
  }

  async refreshConversations(selectId = null) {
    await this.loadConversations();

    const targetId =
      selectId ||
      this.currentConversationId ||
      localStorage.getItem(this.activeStorageKey);

    if (
      targetId &&
      this.conversations.some(c => c.conversation_id === targetId)
    ) {
      this.currentConversationId = targetId;
      localStorage.setItem(this.activeStorageKey, targetId);
    }

    this.renderConversationList();
    this.updateChatHeader();
  }

  updateChatHeader() {
    const titleEl = document.querySelector("#activeChatTitle");
    const metaEl = document.querySelector("#activeChatMeta");

    if (!titleEl) {
      return;
    }

    const thread = this.conversations.find(
      c => c.conversation_id === this.currentConversationId
    );

    if (thread) {
      titleEl.textContent = thread.title || "Conversation";
      if (metaEl) {
        const count = thread.message_count || this.messages.length;
        metaEl.textContent = `${count} message${count === 1 ? "" : "s"} in this thread`;
      }
      return;
    }

    titleEl.textContent = "New conversation";
    if (metaEl) {
      metaEl.textContent = "Ask anything about your uploaded documents";
    }
  }

  appendLocalMessage(message) {
    this.messages.push(message);
    this.renderMessages();
    this.scrollMessagesToBottom();
  }

  applyServerTurn(turn) {
    if (turn.conversation_id) {
      this.currentConversationId = turn.conversation_id;
      localStorage.setItem(
        this.activeStorageKey,
        turn.conversation_id
      );
    }

    const existingIndex = this.messages.findIndex(
      m => m.id === turn.id
    );

    if (existingIndex >= 0) {
      this.messages[existingIndex] = turn;
    } else {
      const pendingIndex = this.messages.findIndex(
        m => m.pending && m.question === turn.question
      );

      if (pendingIndex >= 0) {
        this.messages[pendingIndex] = turn;
      } else {
        this.messages.push(turn);
      }
    }

    this.renderMessages();
    this.showLatestSources();
    this.scrollMessagesToBottom();
    void this.refreshConversations(this.currentConversationId);
  }

  renderConversationList() {
    const listEl = document.querySelector("#conversationList");
    if (!listEl) {
      return;
    }

    const threads = this.getFilteredConversations();

    if (!threads.length) {
      listEl.innerHTML = `
        <p class="muted conversation-empty">
          ${this.searchQuery ? "No matching conversations" : "No conversations yet"}
        </p>
      `;
      return;
    }

    listEl.innerHTML = threads.map(thread => {
      const isActive =
        thread.conversation_id === this.currentConversationId;

      const title = escapeHtml(thread.title || "New conversation");
      const when = thread.updated_at
        ? new Date(thread.updated_at).toLocaleString("en-IN", {
            dateStyle: "medium",
            timeStyle: "short",
          })
        : "";

      return `
        <div class="conversation-row">
          <button
            type="button"
            class="conversation-item${isActive ? " active" : ""}"
            data-conversation-id="${escapeHtml(thread.conversation_id)}"
            title="${title}"
          >
            <span class="conversation-title">${title}</span>
            <span class="conversation-meta">
              ${thread.message_count || 0} msgs
              ${when ? " · " + escapeHtml(when) : ""}
            </span>
          </button>
          <button
            type="button"
            class="conversation-delete"
            data-delete-conversation="${escapeHtml(thread.conversation_id)}"
            title="Delete conversation"
            aria-label="Delete conversation"
          >
            &times;
          </button>
        </div>
      `;
    }).join("");
  }

  renderMessages() {
    const container = document.querySelector("#chatMessages");
    if (!container) {
      return;
    }

    if (!this.messages.length) {
      container.innerHTML = `
        <div class="gpt-empty-state">
          <h3>How can I help you today?</h3>
          <p class="muted">Ask a question about your NRSC documents. Your conversation will appear here.</p>
        </div>
      `;
      return;
    }

    const html = [];

    this.messages.forEach(msg => {
      const time = formatMessageTime(msg.created_at);
      const userText = escapeHtml(msg.question || "");

      html.push(`
        <div class="message-row message-row-user">
          <div class="message-stack">
            <div class="bubble bubble-user">${userText}</div>
            <span class="bubble-time">${escapeHtml(time)}</span>
          </div>
        </div>
      `);

      if (msg.pending) {
        html.push(`
          <div class="message-row message-row-assistant">
            <div class="message-stack">
              <div class="bubble bubble-assistant bubble-thinking">
                <span class="spinner"></span>
                Thinking...
              </div>
            </div>
          </div>
        `);
        return;
      }

      const confidenceBadge =
        typeof msg.confidence === "number"
          ? `<span class="bubble-confidence ${getConfidenceClass(msg.confidence)}">${formatConfidence(msg.confidence)}</span>`
          : "";

      const sourceChips = renderSourceChips(
        msg.sources || [],
        msg.confidence
      );

      html.push(`
        <div class="message-row message-row-assistant">
          <div class="message-stack">
            <div class="bubble-meta">
              <span class="bubble-role">Assistant</span>
              ${confidenceBadge}
            </div>
            <div class="bubble bubble-assistant">${escapeHtml(msg.answer || "")}</div>
            ${sourceChips ? `<div class="bubble-sources">${sourceChips}</div>` : ""}
            <span class="bubble-time">${escapeHtml(time)}</span>
          </div>
        </div>
      `);
    });

    container.innerHTML = html.join("");
    this.bindSourceChips(container);
  }

  bindSourceChips(container) {
    container.querySelectorAll(".source-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        const fileName = chip.dataset.sourceFile;
        if (typeof showSourcePreview === "function" && fileName) {
          showSourcePreview(fileName);
        }
      });
    });
  }

  showLatestSources() {
    const sourcesEl = document.querySelector("#sources");
    if (!sourcesEl) {
      return;
    }

    const latest = [...this.messages]
      .reverse()
      .find(m => !m.pending && (m.sources?.length || m.answer));

    if (!latest) {
      sourcesEl.innerHTML =
        '<p class="muted">Ask a question to see source documents</p>';
      return;
    }

    renderSourcesPanel(sourcesEl, latest.sources || [], latest.confidence);
  }

  clearSourcesPanel() {
    const sourcesEl = document.querySelector("#sources");
    if (sourcesEl) {
      sourcesEl.innerHTML =
        '<p class="muted">Ask a question to see source documents</p>';
    }
  }

  scrollMessagesToBottom() {
    const container = document.querySelector("#chatMessages");
    if (!container) {
      return;
    }

    requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });
  }
}

const chatHistoryManager = new ChatHistoryManager();

function formatMessageTime(value) {
  const date = value ? new Date(value) : new Date();
  return date.toLocaleString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "numeric",
    month: "short",
  });
}

function renderSourceChips(sources, confidence) {
  if (!sources || !sources.length) {
    return "";
  }

  const uniqueSources = [];
  const seenKeys = new Set();

  sources.forEach(source => {
    const fileName =
      source.file || source.filename || source.document || "Unknown";
    const page = source.page || "-";
    const key = `${fileName}|${page}`;

    if (!seenKeys.has(key)) {
      seenKeys.add(key);
      uniqueSources.push({ fileName, page, source });
    }
  });

  return uniqueSources.slice(0, 6).map(item => {
    const label = `${shortFileName(item.fileName)} · p.${item.page}`;
    return `
      <button
        type="button"
        class="source-chip"
        data-source-file="${escapeHtml(item.fileName)}"
        title="${escapeHtml(item.fileName)}"
      >
        ${escapeHtml(label)}
      </button>
    `;
  }).join("");
}

function renderSourcesPanel(sourcesEl, sources, confidence) {
  if (!sources || !sources.length) {
    sourcesEl.innerHTML =
      '<p class="muted">No source citations available.</p>';
    return;
  }

  const uniqueSources = [];
  const seenKeys = new Set();

  sources.forEach(source => {
    const fileName =
      source.file || source.filename || source.document || "Unknown";
    const page = source.page || "0";
    const key = `${fileName}|${page}`;

    if (!seenKeys.has(key)) {
      seenKeys.add(key);
      uniqueSources.push(source);
    }
  });

  sourcesEl.innerHTML = uniqueSources.map(source => {
    const fileName =
      source.file || source.filename || source.document || "Unknown Document";
    const sourceConfidence = source.confidence ?? confidence;

    return `
      <div class="source" data-source-file="${escapeHtml(fileName)}" data-source-page="${source.page || "-"}">
        <strong title="${escapeHtml(fileName)}">${shortFileName(fileName)}</strong>
        <span>Page: ${source.page || "-"}</span>
        <span>Confidence: ${formatConfidence(sourceConfidence)}</span>
      </div>
    `;
  }).join("");

  sourcesEl.querySelectorAll(".source").forEach(sourceEl => {
    sourceEl.addEventListener("click", () => {
      const fileName = sourceEl.dataset.sourceFile;
      if (typeof showSourcePreview === "function") {
        showSourcePreview(fileName);
      }
    });
  });
}

function formatConfidence(confidence) {
  if (typeof confidence !== "number") {
    return "N/A";
  }
  return `${Math.round(confidence * 100)}%`;
}

function getConfidenceClass(confidence) {
  if (confidence >= 0.8) {
    return "confidence-high";
  }
  if (confidence >= 0.5) {
    return "confidence-medium";
  }
  return "confidence-low";
}

function shortFileName(fileName) {
  const safeName = escapeHtml(fileName || "Unknown source");
  if (safeName.length <= 34) {
    return safeName;
  }

  const dotIndex = safeName.lastIndexOf(".");
  const extension = dotIndex > -1 ? safeName.slice(dotIndex) : "";
  return `${safeName.slice(0, 26)}...${extension}`;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
