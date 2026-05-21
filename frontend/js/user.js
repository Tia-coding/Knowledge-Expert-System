

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
    document.querySelector("#chatCount").textContent =
      Array.isArray(conversations) ? conversations.length : 0;

    const metrics = await api("/public-metrics");
    document.querySelector("#docCount").textContent =
      metrics.total_documents || 0;
  } catch (error) {
    console.warn("Failed to update dashboard stats:", error);
    document.querySelector("#docCount").textContent = "0";
    document.querySelector("#chatCount").textContent = "0";
  }
}

// ============================================================
// Quick Ask → Chat
// ============================================================

document.querySelector("#quickAskForm").addEventListener("submit", event => {
  event.preventDefault();

  const question =
    document.querySelector("#quickQuestion").value.trim();

  if (!question) {
    toast("Please enter a question");
    return;
  }

  setActive("ask");
  document.querySelector("#question").value = question;
  document.querySelector("#charCount").textContent = String(question.length);
  autoResizeComposer();

  setTimeout(() => {
    document.querySelector("#askForm").requestSubmit();
  }, 100);
});

// ============================================================
// Composer helpers
// ============================================================

const questionInput = document.querySelector("#question");

function autoResizeComposer() {
  if (!questionInput) {
    return;
  }

  questionInput.style.height = "auto";
  questionInput.style.height = `${Math.min(questionInput.scrollHeight, 160)}px`;
}

questionInput?.addEventListener("input", event => {
  document.querySelector("#charCount").textContent =
    String(event.target.value.length);
  autoResizeComposer();
});

questionInput?.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    document.querySelector("#askForm")?.requestSubmit();
  }
});

// ============================================================
// Ask / Send message
// ============================================================

document.querySelector("#askForm").addEventListener("submit", async event => {
  event.preventDefault();

  const question = questionInput.value.trim();
  const model = document.querySelector("#model").value;

  if (!question) {
    toast("Please enter a message");
    return;
  }

  const submitBtn = document.querySelector(".btn-submit");
  const submitSpinner = document.querySelector("#submitSpinner");
  const submitText = document.querySelector("#submitText");

  const pendingTurn = {
    pending: true,
    question,
    answer: "",
    sources: [],
    confidence: 0,
    created_at: new Date().toISOString(),
  };

  chatHistoryManager.appendLocalMessage(pendingTurn);

  questionInput.value = "";
  document.querySelector("#charCount").textContent = "0";
  autoResizeComposer();

  submitBtn.disabled = true;
  submitSpinner.style.display = "inline-block";
  submitText.textContent = "...";

  const sourcesEl = document.querySelector("#sources");
  if (sourcesEl) {
    sourcesEl.innerHTML =
      '<p class="muted">Finding relevant sources...</p>';
  }

  try {
    const payload = { question, model };

    if (chatHistoryManager.currentConversationId) {
      payload.conversation_id = chatHistoryManager.currentConversationId;
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
      confidence: data.confidence,
      created_at: new Date().toISOString(),
    });

    updateDashboardStats().catch(() => {});

  } catch (error) {
    const errorMsg =
      error.message ||
      "An error occurred while processing your question";

    chatHistoryManager.messages = chatHistoryManager.messages.filter(
      m => !(m.pending && m.question === question)
    );

    chatHistoryManager.appendLocalMessage({
      question,
      answer: `Error: ${errorMsg}`,
      sources: [],
      confidence: 0,
      created_at: new Date().toISOString(),
    });

    if (sourcesEl) {
      sourcesEl.innerHTML =
        '<p class="muted">Error retrieving sources.</p>';
    }

    toast("Error: " + errorMsg);

  } finally {
    submitBtn.disabled = false;
    submitSpinner.style.display = "none";
    submitText.textContent = "Send";
    chatHistoryManager.scrollMessagesToBottom();
    questionInput.focus();
  }
});

// ============================================================
// Sidebar & conversation actions
// ============================================================

async function deleteConversation(conversationId) {
  if (!confirm("Delete this conversation?")) {
    return;
  }

  try {
    await api(
      `/history/conversation/${encodeURIComponent(conversationId)}`,
      { method: "DELETE" }
    );

    toast("Conversation deleted");

    if (chatHistoryManager.currentConversationId === conversationId) {
      chatHistoryManager.startNewConversation();
    }

    await chatHistoryManager.refreshConversations();
    updateDashboardStats().catch(() => {});

  } catch (error) {
    toast("Error: " + error.message);
  }
}

document.querySelector("#newChatBtn")?.addEventListener("click", () => {
  chatHistoryManager.startNewConversation();
  setActive("ask");
  questionInput?.focus();
});

document.querySelector("#conversationSearch")?.addEventListener("input", event => {
  chatHistoryManager.setSearchQuery(event.target.value);
});

document.querySelector("#clearHistoryBtn")?.addEventListener("click", async () => {
  if (!confirm("Delete ALL chat history? This cannot be undone.")) {
    return;
  }

  try {
    await api("/history", { method: "DELETE" });

    chatHistoryManager.startNewConversation();
    await chatHistoryManager.refreshConversations();

    toast("All conversations cleared");
    updateDashboardStats().catch(() => {});

  } catch (error) {
    toast("Error: " + error.message);
  }
});

document.querySelector("#conversationList")?.addEventListener("click", event => {
  const deleteBtn = event.target.closest("[data-delete-conversation]");
  if (deleteBtn) {
    event.stopPropagation();
    deleteConversation(deleteBtn.dataset.deleteConversation);
    return;
  }

  const item = event.target.closest("[data-conversation-id]");
  if (!item) {
    return;
  }

  chatHistoryManager.openConversation(item.dataset.conversationId);
});

document.querySelector("#toggleSourcesBtn")?.addEventListener("click", () => {
  const panel = document.querySelector("#sourcesPanel");
  const btn = document.querySelector("#toggleSourcesBtn");
  const collapsed = document.body.classList.toggle("gpt-sources-collapsed");

  if (panel && btn) {
    btn.setAttribute("aria-expanded", String(!collapsed));
    btn.textContent = collapsed ? "Show sources" : "Sources";
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
});

// ============================================================
// Source Preview Modal
// ============================================================

function openSourcePreview() {
  document.querySelector("#sourcePreviewModal")?.classList.remove("hidden");
}

function closeSourcePreview() {
  document.querySelector("#sourcePreviewModal")?.classList.add("hidden");
}

async function showSourcePreview(fileName) {
  try {
    openSourcePreview();

    const body = document.querySelector("#sourcePreviewBody");
    const title = document.querySelector("#sourcePreviewTitle");
    const meta = document.querySelector("#sourcePreviewMeta");

    title.textContent = fileName || "Document";
    meta.innerHTML = "Loading content...";
    body.innerHTML = `
      <div class="source-loading">
        Loading document content...
      </div>
    `;

    try {
      const response = await api(
        `/documents/search?q=${encodeURIComponent(fileName)}`
      );
      const snippets = response.snippets || [];

      if (snippets.length > 0) {
        meta.innerHTML = `${snippets.length} snippet(s) found`;
        body.innerHTML = snippets
          .slice(0, 10)
          .map(snippet => `
            <div class="snippet-card">
              <div class="snippet-page">
                Page: ${escapeHtml(snippet.page || "-")}
              </div>
              <div class="snippet-text">
                ${escapeHtml(snippet.text || "")}
              </div>
            </div>
          `)
          .join("");
      } else {
        meta.innerHTML = "No content available";
        body.innerHTML = `
          <div class="sources-empty">
            This document is indexed but no snippet previews are available.
          </div>
        `;
      }
    } catch {
      meta.innerHTML = "Preview not available";
      body.innerHTML = `
        <div class="sources-empty">
          Could not load preview for this document.
        </div>
      `;
    }
  } catch (error) {
    console.error("Error loading source preview:", error);
  }
}

document.querySelector(".source-preview-overlay")?.addEventListener("click", closeSourcePreview);
document.querySelector("#closeSourcePreview")?.addEventListener("click", closeSourcePreview);

document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    closeSourcePreview();
  }
});
