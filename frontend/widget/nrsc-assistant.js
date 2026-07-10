class NRSCAssistantWidget {

    constructor(config = {}) {

    this.isOpen = false;

    this.isMaximized = false;

    this.conversationId = null;

    this.config = {

        apiBase: "/api/public",

        askEndpoint: "/ask",

        documentEndpoint: "/document",

        model: "llama3.2:3b",

        title: "NRSC Assistant",

        ...config

    };

    this.model = this.config.model;

    this.createWidget();

    this.messagesContainer =
        document.getElementById("nrsc-messages");

    this.attachEvents();

}

    createWidget() {

        const widget = document.createElement("div");

        widget.innerHTML = `

        <div id="nrsc-launcher" class="nrsc-launcher">
            💬
        </div>

        <div id="nrsc-panel" class="nrsc-panel">

            <div class="nrsc-header">

                <span>
                    ${this.config.title}
                </span>

                <div class="nrsc-buttons">

                    <button id="nrsc-maximize">□</button>

                    <button id="nrsc-close">✕</button>

                </div>

            </div>

            <div id="nrsc-messages" class="nrsc-messages">

                <div class="assistant-message">

                    👋 Hello!

                    <br><br>

                    How can I help you today?

                </div>

            </div>

            <div class="nrsc-input-area">

                <input
                    id="nrsc-input"
                    type="text"
                    placeholder="Ask anything..."
                >

                <button id="nrsc-send">

                    Send

                </button>

            </div>

        </div>

        `;

        document.body.appendChild(widget);

    }

    async askBackend(question) {

        const payload = {
            question: question,
            model: this.model
        };

        if (this.conversationId) {
            payload.conversation_id = this.conversationId;
        }
/* Added api/public/ask instead of api/ask */
        const response = await fetch(

    `${this.config.apiBase}${this.config.askEndpoint}`,

    {

        method: "POST",

        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify(payload)

    }

);

        const data = await response.json();

        //console.log(data);
       // console.log("FULL RESPONSE:", data);
       // console.log("SOURCES:", data.sources);

        if (data.conversation_id) {
            this.conversationId = data.conversation_id;
        }

        return data;

    }
    addUserMessage(message) {

    const div =
        document.createElement("div");

    div.className = "user-message";

    div.textContent = message;

    this.messagesContainer.appendChild(div);

    this.scrollToBottom();

}
 addAssistantMessage(answer, sources = []) {

    const div = document.createElement("div");

    div.className = "assistant-message";

    let html = `

        <div class="assistant-answer">

            ${answer.replace(/\n/g,"<br>")}

        </div>

    `;

    if (sources && sources.length > 0) {

    html += `

        <div class="assistant-sources">

    `;

    sources.forEach((source) => {

        let fileName = source.file
            .replace(".pdf", "")
            .replace("(PDFDrive.com)-min", "")
            .replace("Introduction to ", "")
            .trim();

        if (fileName.length > 28) {
            fileName = fileName.substring(0, 28) + "...";
        }

        html += `

            <button
                class="nrsc-source-chip nrsc-source-link"

                data-document="${source.document_id}"

                data-page="${source.page}">

                📘 ${fileName} · p.${source.page}

            </button>

        `;

    });

    html += `

        </div>

    `;

}

    div.innerHTML = html;
    //Added the changed line here

    div.querySelectorAll(".nrsc-source-link").forEach(link => {

    link.addEventListener("click", async (event) => {

        event.preventDefault();

        const documentId =
            link.dataset.document;

        const page =
            link.dataset.page;

        await this.openSourceDocument(
            documentId,
            page
        );

    });

});

    this.messagesContainer.appendChild(div);

    this.scrollToBottom();
    

}

    showTyping() {
    
    if (document.getElementById("typing-indicator")) {

        return;

    }

    const div = document.createElement("div");

    div.className = "assistant-message";

    div.id = "typing-indicator";

    div.innerHTML = `
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
    `;

    this.messagesContainer.appendChild(div);

    this.scrollToBottom();

}
    hideTyping() {

    const typing =
        document.getElementById("typing-indicator");

    if (typing) {

        typing.remove();

    }

}
    scrollToBottom() {

    this.messagesContainer.scrollTop =
        this.messagesContainer.scrollHeight;

}
async openSourceDocument(documentId, page) {

    try {

        const response = await fetch(

    `${this.config.apiBase}${this.config.documentEndpoint}/${documentId}`

    );

        if (!response.ok) {
            throw new Error("Unable to open document.");
        }

        const blob = await response.blob();

        let blobUrl = URL.createObjectURL(blob);

        if (blob.type === "application/pdf") {
            blobUrl += `#page=${page}`;
        }

        window.open(blobUrl, "_blank");

    }

    catch (error) {

        console.error(error);

        alert("Unable to open document.");

    }

}
    async sendMessage(input, sendBtn) {

    const question = input.value.trim();

    if (!question) return;

    this.addUserMessage(question);

    sendBtn.disabled = true;
    input.disabled = true;

    input.value = "";

    this.showTyping();

    try {

        const response = await this.askBackend(question);

        this.hideTyping();

        sendBtn.disabled = false;

        input.disabled = false;

        input.focus();

        this.addAssistantMessage(
            response.answer,
            response.sources
        );

    }

    catch (error) {

        this.hideTyping();

        sendBtn.disabled = false;

        input.disabled = false;

        input.focus();

        this.addAssistantMessage(
            "Something went wrong."
        );

        console.error(error);

    }

}
    attachEvents() {

        const launcher = document.getElementById("nrsc-launcher");

        const panel = document.getElementById("nrsc-panel");

        const closeBtn = document.getElementById("nrsc-close");

        const maximizeBtn = document.getElementById("nrsc-maximize");

        const sendBtn = document.getElementById("nrsc-send");

        const input = document.getElementById("nrsc-input");

        launcher.onclick = () => {

            panel.style.display = "flex";

            launcher.style.display = "none";

            input.focus();

        };

        closeBtn.onclick = () => {

            panel.style.display = "none";

            launcher.style.display = "flex";

            input.value= "";

            this.hideTyping();

            sendBtn.disabled = false;
            input.disabled = false;

        };
        maximizeBtn.onclick = () => {

            this.isMaximized = !this.isMaximized;

            panel.classList.toggle("nrsc-maximized");

            maximizeBtn.textContent =
                this.isMaximized ? "❐" : "□";

        };
        sendBtn.onclick = async () => {

            await this.sendMessage(input, sendBtn);

        };

    input.addEventListener("keypress", (event) => {

        if (event.key === "Enter") {

            sendBtn.click();

        }

});
     document.addEventListener("keydown", (event) => {

        if (event.key === "Escape" && panel.style.display === "flex") {

            panel.style.display = "none";

            launcher.style.display = "flex";

            input.value = "";

            this.hideTyping();

            sendBtn.disabled = false;
            input.disabled = false;

        }

});
    }

}
// Change the confirigation here
window.onload = () => {

    new NRSCAssistantWidget({

        apiBase: "/api/public",

        askEndpoint: "/ask",

        documentEndpoint: "/document",

        title: "NRSC Assistant",

        model: "llama3.2:3b"

    });

};