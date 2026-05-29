class ChatHistoryManager {
  constructor() {
    this.currentConversationId = null;
    this.conversations = [];
    this.messages = [];
    this.searchQuery = "";
    this.activeStorageKey = "nrsc_active_conversation_id";
    this.titleStorageKey = "nrsc_conversation_titles";
  }

  getCustomTitles() {
    try {
      return JSON.parse(
        localStorage.getItem(this.titleStorageKey) || "{}"
      );
    } catch {
      return {};
    }
  }

  getConversationTitle(conversationId) {
    const custom = this.getCustomTitles()[conversationId];
    if (custom) {
      return custom;
    }

    const thread = this.conversations.find(
      c => c.conversation_id === conversationId
    );

    return thread?.title || "New conversation";
  }

  setConversationTitle(conversationId, title) {
    const titles = this.getCustomTitles();
    titles[conversationId] = title;
    localStorage.setItem(
      this.titleStorageKey,
      JSON.stringify(titles)
    );
  }

  removeConversationTitle(conversationId) {
    const titles = this.getCustomTitles();
    delete titles[conversationId];
    localStorage.setItem(
      this.titleStorageKey,
      JSON.stringify(titles)
    );
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
      this.getConversationTitle(thread.conversation_id)
        .toLowerCase()
        .includes(this.searchQuery)
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
      titleEl.textContent = this.getConversationTitle(
        thread.conversation_id
      );
      if (metaEl) {
        metaEl.textContent = "NRSC Knowledge Assistant";
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

      const conversationId = escapeHtml(thread.conversation_id);
      const title = escapeHtml(
        this.getConversationTitle(thread.conversation_id)
      );

      return `
        <div class="conversation-row${isActive ? " active" : ""}">
          <button
            type="button"
            class="conversation-item${isActive ? " active" : ""}"
            data-conversation-id="${conversationId}"
            title="${title}"
          >
            <span class="conversation-title">${title}</span>
          </button>
          <div class="conversation-menu-wrap">
            <button
              type="button"
              class="conversation-menu-btn"
              data-menu-toggle="${conversationId}"
              aria-label="Conversation options"
              aria-haspopup="true"
            >
              ⋮
            </button>
            <div
              class="conversation-dropdown"
              data-menu="${conversationId}"
              hidden
            >
              <button
                type="button"
                class="conversation-dropdown-item"
                data-rename-conversation="${conversationId}"
              >
                Rename
              </button>
              <button
                type="button"
                class="conversation-dropdown-item danger"
                data-delete-conversation="${conversationId}"
              >
                Delete
              </button>
            </div>
          </div>
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

      const sourceChips = renderSourceChips(msg.sources || []);

      html.push(`
        <div class="message-row message-row-assistant">
          <div class="message-stack">
            <div class="bubble-meta">
              <span class="bubble-role">Assistant</span>
            </div>
            <div class="bubble bubble-assistant">${renderFormattedAnswer(msg.answer || "")}</div>
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
        const page = chip.dataset.sourcePage;
        if (typeof openSourceDocument === "function" && fileName) {
          openSourceDocument(fileName, page);
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

    renderSourcesPanel(sourcesEl, latest.sources || []);
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

function renderSourceChips(sources) {
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
        data-source-page="${escapeHtml(String(item.page))}"
        title="${escapeHtml(item.fileName)} · Page ${escapeHtml(String(item.page))}"
      >
        ${escapeHtml(label)}
      </button>
    `;
  }).join("");
}

function renderSourcesPanel(sourcesEl, sources) {
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

    return `
      <div class="source" data-source-file="${escapeHtml(fileName)}" data-source-page="${source.page || "-"}">
        <strong title="${escapeHtml(fileName)}">${shortFileName(fileName)}</strong>
        <span>Page ${source.page || "-"}</span>
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

function renderFormattedAnswer(text) {
  if (!text) {
    return "";
  }

  const normalized = String(text)
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1");

  const lines = normalized.split("\n");
  const parts = [];
  let listType = null;
  let tableRows = [];
  let pseudoLines = [];
  let inPseudoSection = false;

  function flushPseudoBlock() {
    if (!pseudoLines.length) {
      inPseudoSection = false;
      return;
    }
    parts.push(
      `<pre class="answer-code"><code>${escapeHtml(pseudoLines.join("\n"))}</code></pre>`
    );
    pseudoLines = [];
    inPseudoSection = false;
  }

  function closeList() {
    if (listType === "ul") {
      parts.push("</ul>");
    } else if (listType === "ol") {
      parts.push("</ol>");
    }
    listType = null;
  }

  function flushTable() {
    if (!tableRows.length) {
      return;
    }

    const rows = tableRows
      .map(row =>
        row
          .split("|")
          .map(cell => cell.trim())
          .filter(Boolean)
      )
      .filter(cells => cells.length >= 2);

    tableRows = [];

    if (!rows.length) {
      return;
    }

    const header = rows[0];
    const body = rows.slice(1);

    parts.push('<div class="answer-table-wrap"><table class="answer-table">');
    parts.push(
      `<thead><tr>${header.map(cell => `<th>${escapeHtml(cell)}</th>`).join("")}</tr></thead>`
    );
    parts.push("<tbody>");
    body.forEach(cells => {
      parts.push(
        `<tr>${cells.map(cell => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`
      );
    });
    parts.push("</tbody></table></div>");
  }

  lines.forEach(line => {
    const trimmed = line.trim();

    if (!trimmed) {
      if (inPseudoSection) {
        pseudoLines.push("");
        return;
      }
      closeList();
      flushTable();
      flushPseudoBlock();
      return;
    }

    if (inPseudoSection) {
      const nestedSection = trimmed.match(
        /^([A-Za-z][A-Za-z0-9 /&]+):\s*(.*)$/
      );
      if (nestedSection && nestedSection[1].length <= 45) {
        flushPseudoBlock();
      } else {
        pseudoLines.push(trimmed);
        return;
      }
    }

    if (trimmed.includes("|") && trimmed.split("|").length >= 3) {
      if (/^[\s|:-]+$/.test(trimmed.replace(/\|/g, ""))) {
        return;
      }
      closeList();
      tableRows.push(trimmed);
      return;
    }

    if (tableRows.length) {
      flushTable();
    }

    const sectionMatch = trimmed.match(
      /^([A-Za-z][A-Za-z0-9 /&]+):\s*(.*)$/
    );

    if (sectionMatch && sectionMatch[1].length <= 45) {
      closeList();
      flushPseudoBlock();
      const title = sectionMatch[1];
      const rest = sectionMatch[2];
      inPseudoSection = /pseudo\s*code/i.test(title);
      parts.push(
        `<h4 class="answer-heading">${escapeHtml(title)}</h4>`
      );
      if (rest) {
        if (inPseudoSection) {
          pseudoLines.push(rest);
        } else {
          parts.push(`<p class="answer-p">${escapeHtml(rest)}</p>`);
        }
      }
      return;
    }

    const numberedMatch = trimmed.match(/^(\d+)\.\s+(.+)$/);
    if (numberedMatch) {
      if (listType !== "ol") {
        closeList();
        parts.push('<ol class="answer-list answer-list-ordered">');
        listType = "ol";
      }
      parts.push(`<li>${escapeHtml(numberedMatch[2])}</li>`);
      return;
    }

    const bulletMatch = trimmed.match(/^[-•*]\s+(.+)$/);
    if (bulletMatch) {
      if (listType !== "ul") {
        closeList();
        parts.push('<ul class="answer-list">');
        listType = "ul";
      }
      parts.push(`<li>${escapeHtml(bulletMatch[1])}</li>`);
      return;
    }

    if (
      /^(for|while|if|else|return|def |function |procedure |begin\b|end\b|loop\b)/i.test(
        trimmed
      ) ||
      (trimmed.endsWith(";") && trimmed.length < 120)
    ) {
      closeList();
      parts.push(
        `<pre class="answer-code"><code>${escapeHtml(trimmed)}</code></pre>`
      );
      return;
    }

    closeList();
    parts.push(`<p class="answer-p">${escapeHtml(trimmed)}</p>`);
  });

  closeList();
  flushTable();
  flushPseudoBlock();

  return `<div class="answer-content">${parts.join("")}</div>`;
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
