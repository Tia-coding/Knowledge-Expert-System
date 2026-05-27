guard("user");

// ============================================================
// Navigation
// ============================================================

document.querySelectorAll(".nav-item[data-section]").forEach(item => {
  item.addEventListener("click", event => {
    event.preventDefault();

    const section = item.dataset.section;
    setActive(section);

    if (section === "dashboard") {
      updateDashboardStats();
    } else if (section === "ask") {
      chatHistoryManager.scrollMessagesToBottom();
    }
  });
});

document.querySelectorAll("[data-logout]").forEach(btn => {
  btn.addEventListener("click", logout);
});

// ============================================================
// Dashboard Stats
// ============================================================

async function updateDashboardStats() {
  try {
    const conversations = await api("/history/conversations");

    const chatCount = document.querySelector("#chatCount");
    if (chatCount) {
      chatCount.textContent =
        Array.isArray(conversations) ? conversations.length : 0;
    }

    const metrics = await api("/public-metrics");

    const docCount = document.querySelector("#docCount");
    if (docCount) {
      docCount.textContent = metrics.total_documents || 0;
    }

  } catch (error) {
    console.warn("Failed to update dashboard stats:", error);
  }
}

// ============================================================
// Composer
// ============================================================

const questionInput = document.querySelector("#question");

function autoResizeComposer() {
  if (!questionInput) return;

  questionInput.style.height = "24px";
  questionInput.style.height =
    Math.min(questionInput.scrollHeight, 180) + "px";
}

questionInput?.addEventListener("input", () => {
  autoResizeComposer();
});

questionInput?.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();

    document.querySelector("#askForm")?.requestSubmit();
  }
});

// ============================================================
// Ask Question
// ============================================================

document.querySelector("#askForm")?.addEventListener("submit", async event => {
  event.preventDefault();

  const question = questionInput.value.trim();

  if (!question) {
    toast("Please enter a message");
    return;
  }

  const model =
    document.querySelector("#model")?.value || "llama3";

  const submitBtn = document.querySelector(".btn-submit");
  const submitText = document.querySelector("#submitText");
  const submitSpinner = document.querySelector("#submitSpinner");

  submitBtn.disabled = true;

  if (submitSpinner) {
    submitSpinner.style.display = "inline-block";
  }

  if (submitText) {
    submitText.textContent = "";
  }

  // Add pending message

  chatHistoryManager.appendLocalMessage({
    pending: true,
    question,
    answer: "",
    sources: [],
    confidence: 0,
    created_at: new Date().toISOString(),
  });

  // Clear input

  questionInput.value = "";
  autoResizeComposer();

  try {
    const payload = {
      question,
      model,
    };

    if (chatHistoryManager.currentConversationId) {
      payload.conversation_id =
        chatHistoryManager.currentConversationId;
    }

    const data = await api("/ask", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (!data.answer) {
      throw new Error("No answer received from server");
    }

    chatHistoryManager.applyServerTurn({
      id: data.id,
      conversation_id: data.conversation_id,
      question,
      answer: data.answer,
      sources: data.sources || [],
      confidence: data.confidence || 0,
      created_at: new Date().toISOString(),
    });

    updateDashboardStats().catch(() => {});

  } catch (error) {

    const errorMsg =
      error.message ||
      "An error occurred while processing your question";

    // remove pending

    chatHistoryManager.messages =
      chatHistoryManager.messages.filter(
        m => !(m.pending && m.question === question)
      );

    // show error

    chatHistoryManager.appendLocalMessage({
      question,
      answer: `Error: ${errorMsg}`,
      sources: [],
      confidence: 0,
      created_at: new Date().toISOString(),
    });

    toast(errorMsg);

  } finally {

    submitBtn.disabled = false;

    if (submitSpinner) {
      submitSpinner.style.display = "none";
    }

    if (submitText) {
      submitText.textContent = "↑";
    }

    chatHistoryManager.scrollMessagesToBottom();

    questionInput.focus();
  }
});

// ============================================================
// Conversations
// ============================================================

function closeAllConversationMenus() {
  document.querySelectorAll(".conversation-dropdown").forEach(menu => {
    menu.hidden = true;
  });

  document.querySelectorAll(".conversation-row").forEach(row => {
    row.classList.remove("menu-open");
  });
}

async function deleteConversation(conversationId) {

  if (!confirm("Delete this conversation?")) {
    return;
  }

  try {

    await api(
      `/history/conversation/${encodeURIComponent(conversationId)}`,
      {
        method: "DELETE",
      }
    );

    chatHistoryManager.removeConversationTitle(conversationId);
    toast("Conversation deleted");

    if (
      chatHistoryManager.currentConversationId === conversationId
    ) {
      chatHistoryManager.startNewConversation();
    }

    await chatHistoryManager.refreshConversations();
    closeAllConversationMenus();

  } catch (error) {
    toast(error.message);
  }
}

function renameConversation(conversationId) {
  const currentTitle =
    chatHistoryManager.getConversationTitle(conversationId);

  const newTitle = prompt(
    "Rename conversation",
    currentTitle
  );

  if (newTitle === null) {
    return;
  }

  const trimmed = newTitle.trim();

  if (!trimmed) {
    toast("Title cannot be empty");
    return;
  }

  chatHistoryManager.setConversationTitle(
    conversationId,
    trimmed
  );

  chatHistoryManager.renderConversationList();
  chatHistoryManager.updateChatHeader();
  closeAllConversationMenus();
  toast("Conversation renamed");
}

document.querySelector("#newChatBtn")?.addEventListener("click", () => {

  chatHistoryManager.startNewConversation();

  questionInput?.focus();
});

document.querySelector("#conversationSearch")
?.addEventListener("input", event => {

  chatHistoryManager.setSearchQuery(event.target.value);
});

document.querySelector("#clearHistoryBtn")
?.addEventListener("click", async () => {

  if (!confirm("Delete ALL chat history?")) {
    return;
  }

  try {

    await api("/history", {
      method: "DELETE",
    });

    chatHistoryManager.startNewConversation();

    await chatHistoryManager.refreshConversations();

    toast("All chats cleared");

  } catch (error) {
    toast(error.message);
  }
});

document.querySelector("#conversationList")
?.addEventListener("click", event => {

  const menuToggle =
    event.target.closest("[data-menu-toggle]");

  if (menuToggle) {
    event.stopPropagation();

    const row = menuToggle.closest(".conversation-row");
    const menu = row?.querySelector(".conversation-dropdown");
    const willOpen = menu?.hidden !== false;

    closeAllConversationMenus();

    if (willOpen && menu && row) {
      menu.hidden = false;
      row.classList.add("menu-open");
    }

    return;
  }

  const renameBtn =
    event.target.closest("[data-rename-conversation]");

  if (renameBtn) {
    event.stopPropagation();
    renameConversation(
      renameBtn.dataset.renameConversation
    );
    return;
  }

  const deleteBtn =
    event.target.closest("[data-delete-conversation]");

  if (deleteBtn) {
    event.stopPropagation();

    deleteConversation(
      deleteBtn.dataset.deleteConversation
    );

    return;
  }

  const item =
    event.target.closest("[data-conversation-id]");

  if (!item) return;

  closeAllConversationMenus();

  chatHistoryManager.openConversation(
    item.dataset.conversationId
  );
});

document.addEventListener("click", event => {
  if (!event.target.closest("#conversationList")) {
    closeAllConversationMenus();
  }
});

// ============================================================
// Source Preview / Open Document Page
// ============================================================

async function openSourceDocument(fileName, page) {
  try {
    const params = new URLSearchParams({
      q: fileName,
    });

    if (page && String(page) !== "-") {
      params.set("page", String(page));
    }

    const response = await api(`/documents/search?${params.toString()}`);

    if (!response.document_id) {
      toast("Document not found");
      return;
    }

    const viewResponse = await fetch(
      `/api/documents/view/${response.document_id}`,
      { headers: authHeaders() }
    );

    if (viewResponse.status === 401 || viewResponse.status === 403) {
      clearAuthSession();
      location.href = "/index.html";
      return;
    }

    if (!viewResponse.ok) {
      throw new Error("Could not open document");
    }

    const blob = await viewResponse.blob();
    let blobUrl = URL.createObjectURL(blob);

    const isPdf = (response.filename || fileName || "")
      .toLowerCase()
      .endsWith(".pdf");

    if (isPdf && page && String(page) !== "-") {
      blobUrl += `#page=${encodeURIComponent(String(page))}`;
    }

    window.open(blobUrl, "_blank");

    setTimeout(() => {
      URL.revokeObjectURL(blobUrl);
    }, 120000);
  } catch (error) {
    console.error(error);
    toast(error.message || "Failed to open source document");
  }
}

function openSourcePreview() {
  document.querySelector("#sourcePreviewModal")
    ?.classList.remove("hidden");
}

function closeSourcePreview() {
  document.querySelector("#sourcePreviewModal")
    ?.classList.add("hidden");
}

async function showSourcePreview(fileName, page) {

  try {

    openSourcePreview();

    const body =
      document.querySelector("#sourcePreviewBody");

    const title =
      document.querySelector("#sourcePreviewTitle");

    const meta =
      document.querySelector("#sourcePreviewMeta");

    title.textContent = fileName || "Document";

    meta.innerHTML = "Loading...";

    body.innerHTML = `
      <div class="source-loading">
        Loading document content...
      </div>
    `;

    const params = new URLSearchParams({
      q: fileName,
    });

    if (page && String(page) !== "-") {
      params.set("page", String(page));
    }

    const response = await api(
      `/documents/search?${params.toString()}`
    );

    const snippets = response.snippets || [];

    if (snippets.length > 0) {

      meta.innerHTML =
        `${snippets.length} snippet(s) found`;

      body.innerHTML =
        snippets.slice(0, 10).map(snippet => `
          <div class="snippet-card">
            <div class="snippet-page">
              Page: ${escapeHtml(snippet.page || "-")}
            </div>

            <div class="snippet-text">
              ${escapeHtml(snippet.text || "")}
            </div>
          </div>
        `).join("");

    } else {

      meta.innerHTML = "No preview available";

      body.innerHTML = `
        <div class="sources-empty">
          No snippets available.
        </div>
      `;
    }

  } catch (error) {

    console.error(error);

    const body =
      document.querySelector("#sourcePreviewBody");

    if (body) {
      body.innerHTML = `
        <div class="sources-empty">
          Failed to load preview.
        </div>
      `;
    }
  }
}

document.querySelector(".source-preview-overlay")
?.addEventListener("click", closeSourcePreview);

document.querySelector("#closeSourcePreview")
?.addEventListener("click", closeSourcePreview);

document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    closeSourcePreview();
  }
});

// ============================================================
// Initialize
// ============================================================

window.addEventListener("DOMContentLoaded", () => {

  chatHistoryManager.init().catch(error => {
    console.error("Chat init failed:", error);
  });

  updateDashboardStats().catch(() => {});

  autoResizeComposer();

  questionInput?.focus();
});