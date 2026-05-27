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

    toast("Conversation deleted");

    if (
      chatHistoryManager.currentConversationId === conversationId
    ) {
      chatHistoryManager.startNewConversation();
    }

    await chatHistoryManager.refreshConversations();

  } catch (error) {
    toast(error.message);
  }
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

  chatHistoryManager.openConversation(
    item.dataset.conversationId
  );
});

// ============================================================
// Source Preview
// ============================================================

function openSourcePreview() {
  document.querySelector("#sourcePreviewModal")
    ?.classList.remove("hidden");
}

function closeSourcePreview() {
  document.querySelector("#sourcePreviewModal")
    ?.classList.add("hidden");
}

async function showSourcePreview(fileName) {

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

    const response = await api(
      `/documents/search?q=${encodeURIComponent(fileName)}`
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