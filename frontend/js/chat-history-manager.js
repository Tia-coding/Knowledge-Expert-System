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
            <div class="bubble bubble-assistant">${renderFormattedAnswer(msg.answer || "", msg.question || "")}</div>
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

// ============================================================
// IMPROVED MARKDOWN RENDERER
// ============================================================

/**
 * Renders markdown text to HTML with full support for:
 * - Bold (**text**)
 * - Italic (*text*)
 * - Inline code (`code`)
 * - Code blocks (```code```)
 * - Tables (| col1 | col2 |)
 * - Headings (## Heading)
 * - Ordered lists (1. item)
 * - Unordered lists (- item / * item)
 * - Nested lists (indented)
 * - Links ([text](url))
 */

function markdownToHtml(markdown) {
  if (!markdown) return "";

  let html = markdown.replace(/\r\n/g, "\n");

  // Step 1: Extract and protect code blocks
  const codeBlocks = [];
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (match, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push({ type: "block", lang, code: code.trim() });
    return `%%CODEBLOCK_${idx}%%`;
  });

  // Step 2: Extract and protect inline code
  const inlineCodes = [];
  html = html.replace(/`([^`]+)`/g, (match, code) => {
    const idx = inlineCodes.length;
    inlineCodes.push(code);
    return `%%INLINECODE_${idx}%%`;
  });

  // Step 3: Process tables (protect them from other transformations)
  const tables = [];
  html = html.replace(/(\|[^\n]*\|\s*\n)(?:\|[^\n]*\|[\s:|-]*\n)?(\|(?:[^\n]*\|[\s\S]*?)(?:\n|$))/gm, (match) => {
    // Collect all consecutive table lines
    const lines = match.split("\n").filter(l => l.trim().startsWith("|"));
    if (lines.length < 2) return match;
    const idx = tables.length;
    tables.push(lines);
    return `%%TABLE_${idx}%%`;
  });
  // Also catch tables that start with | immediately after a newline
  html = html.replace(/((?:^|\n)\|[^\n]*\|\s*\n(?:\|[^\n]*\|\s*\n)+)/g, (match) => {
    const lines = match.trim().split("\n").filter(l => l.trim().startsWith("|"));
    if (lines.length < 2) return match;
    const idx = tables.length;
    tables.push(lines);
    return `\n%%TABLE_${idx}%%`;
  });

  // Step 4: Process headings (but not bold text that looks like headings)
  html = html.replace(/^####\s+(.+)$/gm, '<h4 class="answer-heading">$1</h4>');
  html = html.replace(/^###\s+(.+)$/gm, '<h3 class="answer-heading">$1</h3>');
  html = html.replace(/^##\s+(.+)$/gm, '<h2 class="answer-heading">$1</h2>');

  // Step 5: Process horizontal rules
  html = html.replace(/^---+\s*$/gm, '<hr class="answer-hr">');

  // Step 6: Convert markdown links to HTML
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener" class="answer-link">$1</a>');

  // Step 7: Convert bold and italic (BEFORE escaping HTML to preserve markdown syntax)
  html = html.replace(
    /\*\*([^*]+)\*\*/g,
    '<strong>$1</strong>'
  );
  html = html.replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, '<em>$1</em>');

  // Step 8: Escape remaining HTML entities in non-code parts
  // We need to escape but not in code blocks/tables/inline codes
  // Temporarily replace protected tokens, escape, then restore

  

  // Step 9: Process lists (ordered and unordered with nesting)
  // First wrap each line in a list structure parser
  const lines = html.split("\n");
  const listHtml = [];
  let inOrderedList = false;
  let inUnorderedList = false;
  let listStack = []; // Track nesting for nested lists

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Check for protected blocks
    if (line.trim().startsWith("%%CODEBLOCK_") || line.trim().startsWith("%%TABLE_")) {
      // Close any open lists
      if (inOrderedList) { listHtml.push("</ol>"); inOrderedList = false; }
      if (inUnorderedList) { listHtml.push("</ul>"); inUnorderedList = false; }
      listHtml.push(line);
      continue;
    }

    // Check for heading or hr
    if (line.trim().startsWith("<h")) {
      if (inOrderedList) { listHtml.push("</ol>"); inOrderedList = false; }
      if (inUnorderedList) { listHtml.push("</ul>"); inUnorderedList = false; }
      listHtml.push(line);
      continue;
    }

    if (line.trim().startsWith("<hr")) {
      if (inOrderedList) { listHtml.push("</ol>"); inOrderedList = false; }
      if (inUnorderedList) { listHtml.push("</ul>"); inUnorderedList = false; }
      listHtml.push(line);
      continue;
    }

    // Check for empty line
    if (!line.trim()) {
      if (inOrderedList) { listHtml.push("</ol>"); inOrderedList = false; }
      if (inUnorderedList) { listHtml.push("</ul>"); inUnorderedList = false; }
      listHtml.push("");
      continue;
    }

    // Determine indentation level for nesting
    const indent = line.search(/\S/);
    const trimmed = line.trim();

    // Ordered list: starts with number followed by period
    const orderedMatch = trimmed.match(/^(\d+)\.\s+(.+)$/);
    // Unordered list: starts with -, *, or •
    const unorderedMatch = trimmed.match(/^[-*•]\s+(.+)$/);

    if (orderedMatch) {
      if (inUnorderedList) { listHtml.push("</ul>"); inUnorderedList = false; }
      if (!inOrderedList) {
        listHtml.push('<ol class="answer-list answer-list-ordered">');
        inOrderedList = true;
      }
      listHtml.push(`<li>${orderedMatch[2].trim()}</li>`);
    } else if (unorderedMatch) {
      if (inOrderedList) { listHtml.push("</ol>"); inOrderedList = false; }
      if (!inUnorderedList) {
        listHtml.push('<ul class="answer-list">');
        inUnorderedList = true;
      }
      listHtml.push(`<li>${unorderedMatch[1].trim()}</li>`);
    } else {
      // Regular paragraph
      if (inOrderedList) { listHtml.push("</ol>"); inOrderedList = false; }
      if (inUnorderedList) { listHtml.push("</ul>"); inUnorderedList = false; }
      
      // Check if this looks like a section heading with colon
      const colonMatch = trimmed.match(/^(<strong>)?([A-Za-z][A-Za-z0-9 /&()\-]+)(<\/strong>)?:\s*(.*)$/);
      if (colonMatch && colonMatch[2].length < 50 && colonMatch[4]) {
        const title = colonMatch[2];
        const rest = colonMatch[4]; // Recursively process the rest
        listHtml.push(`<p class="answer-p"><strong>${title}:</strong> ${rest}</p>`);
      } else if (trimmed.startsWith("%%INLINECODE_")) {
        listHtml.push(`<p class="answer-p">${line}</p>`);
      } else {
        listHtml.push(`<p class="answer-p">${line}</p>`);
      }
    }
  }

  // Close any remaining open lists
  if (inOrderedList) listHtml.push("</ol>");
  if (inUnorderedList) listHtml.push("</ul>");

  html = listHtml.join("\n");

  // Step 10: Restore code blocks
  html = html.replace(/%%CODEBLOCK_(\d+)%%/g, (match, idx) => {
    const block = codeBlocks[parseInt(idx)];
    const lang = block.lang ? ` data-language="${escapeHtml(block.lang)}"` : "";
    const code = escapeHtml(block.code);
    return `<pre class="answer-code"><code${lang}>${code}</code></pre>`;
  });

  // Step 11: Restore inline code
  html = html.replace(/%%INLINECODE_(\d+)%%/g, (match, idx) => {
    const code = escapeHtml(inlineCodes[parseInt(idx)]);
    return `<code class="answer-inline-code">${code}</code>`;
  });

  // Step 12: Restore tables
  html = html.replace(/%%TABLE_(\d+)%%/g, (match, idx) => {
    const lines = tables[parseInt(idx)];
    return renderTableFromLines(lines);
  });

  // Step 13: Clean up - remove excessive blank lines between paragraphs
  html = html.replace(/(<p class="answer-p">)\s*<\/p>/g, "");

  return html;
}

/**
 * Render markdown table lines to HTML table.
 */
function renderTableFromLines(lines) {
  if (!lines || lines.length < 2) return "";

  // Parse each line into cells
  const rows = lines.map(line => {
    return line
      .split("|")
      .map(cell => cell.trim())
      .filter(cell => cell.length > 0);
  }).filter(row => row.length >= 2);

  if (rows.length < 2) return "";

  const headerCells = rows[0];
  
  // Find the separator row (contains ---)
  let separatorIdx = -1;
  for (let i = 1; i < rows.length; i++) {
    if (rows[i].every(cell => /^:?-{3,}:?$/.test(cell))) {
      separatorIdx = i;
      break;
    }
  }

  // Determine the start of body data
  const bodyStartIdx = separatorIdx > 0 ? separatorIdx + 1 : 1;
  const bodyRows = rows.slice(bodyStartIdx);

  if (bodyRows.length === 0) return "";

  // Determine column alignments from separator
  let alignments = [];
  if (separatorIdx > 0) {
    alignments = rows[separatorIdx].map(cell => {
      if (/^:-+:$/.test(cell)) return ' style="text-align:center"';
      if (/^:-+$/.test(cell)) return ' style="text-align:left"';
      if (/:+$/.test(cell)) return ' style="text-align:right"';
      return "";
    });
  }

  let table = '<div class="answer-table-wrap"><table class="answer-table">';
  
  // Header
  table += '<thead><tr>';
  headerCells.forEach((cell, i) => {
    table += `<th${alignments[i] || ""}>${escapeHtml(cell)}</th>`;
  });
  table += '</tr></thead>';
  
  // Body
  table += '<tbody>';
  bodyRows.forEach(row => {
    table += '<tr>';
    // Ensure we don't exceed header column count
    for (let i = 0; i < Math.min(row.length, headerCells.length); i++) {
      table += `<td${alignments[i] || ""}>${escapeHtml(row[i])}</td>`;
    }
    table += '</tr>';
  });
  table += '</tbody></table></div>';

  return table;
}

/**
 * Clean answer text of filler phrases and prepare for markdown rendering.
 */



function removeRepeatedQuestion(answer, question) {
  if (!answer || !question) return answer;

  const normalizedAnswer = answer.trim().toLowerCase();
  const normalizedQuestion = question.trim().toLowerCase();

  if (
    normalizedAnswer.startsWith(normalizedQuestion) ||
    normalizedAnswer.startsWith(normalizedQuestion + "?") ||
    normalizedAnswer.startsWith(normalizedQuestion + ":")
  ) {
    return answer.substring(question.length).trim();
  }

  return answer;
}



function preprocessAnswerDisplay(text) {
  if (!text) return "";
  
  // Remove grounded filler lines
  const fillerLines = [
    /^based on (the )?(uploaded |provided )?documents?[^.]*\.?\s*$/im,
    /^according to (the )?(uploaded |provided )?(notes|pdfs|materials|documents|text|context)[^.]*\.?\s*$/im,
    /^retrieved information shows[^.]*\.?\s*$/im,
    /^the document explains[^.]*\.?\s*$/im,
    /^the (uploaded |provided )?documents (state|indicate|mention|contain|provide)[^.]*\.?\s*$/im,
    /^from the (uploaded |provided )?context[^.]*\.?\s*$/im,
    /^in essence,?\s*$/im,
    /^from a high-level perspective,?\s*$/im,
    /^it can be concluded,?\s*$/im,
    /^therefore we can conclude,?\s*$/im,
    /^the above discussion,?\s*$/im,
    /^as discussed above,?\s*$/im,
    /^here is (the )?(direct )?(answer|response):?\s*$/im,
    /^the (direct )?(answer|response) is:?\s*$/im,
    /^here is (a )?(brief )?(definition|explanation|comparison):?\s*$/im,
    /^here are (some of )?(the )?(key )?(types|features|advantages|disadvantages|categories)?:?\s*$/im,
    /^here is a list of[^:]*:?\s*$/im,
    /^the following (is|are)[^:]*:?\s*$/im,
    /^sure,? here is[^:]*:?\s*$/im,
    /^certainly!?\s*$/im,
    /^of course!?\s*$/im,
    /^i'?d be happy to.*[.!]\s*$/im,
    /^let me provide.*[.!]\s*$/im,
    /^below is[^.]*\.?\s*$/im,
  ];
  
  let lines = text.split("\n");
  let cleaned = [];
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    let skip = false;
    
    for (const pattern of fillerLines) {
      if (pattern.test(trimmed)) {
        skip = true;
        break;
      }
    }
    
    if (!skip) {
      cleaned.push(line);
    }
  }
  
  return cleaned.join("\n");
}

/**
 * Render formatted answer with full markdown support.
 */
function renderFormattedAnswer(text, question = "") {
  if (!text) {
    return "";
  }

  // Clean filler text
  let cleaned = preprocessAnswerDisplay(text);

  // Remove repeated question if model echoes it
  cleaned = removeRepeatedQuestion(
    cleaned,
    question
  );

  // Check if this is a "not found" response
  const notFoundPatterns = [
    "i'm sorry, but i couldn't find the information you're looking for",
    "the requested information was not found in the uploaded documents",
    "i couldn't find the information you're looking for",
    "the information was not found",
    "information was not found",
  ];

  const lowerText = cleaned.toLowerCase().trim();

  const isNotFound = notFoundPatterns.some(
    p => lowerText.startsWith(p) || lowerText === p
  );

  if (isNotFound) {
    return `
      <div class="answer-content answer-not-found">
        <p>${escapeHtml(cleaned)}</p>
      </div>
    `;
  }

  // Convert markdown to HTML
  const html = markdownToHtml(cleaned);

  return `
    <div class="answer-content">
      ${html}
    </div>
  `;
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
  const el = document.createElement("div");
  el.textContent = String(value || "");
  return el.innerHTML;
}
