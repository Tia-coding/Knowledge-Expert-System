# Knowledge Expert System (RAG)

A configurable Retrieval-Augmented Generation (RAG) based Knowledge Expert System developed during my internship at the National Remote Sensing Centre (NRSC), ISRO, Hyderabad.

The system enables semantic document retrieval, grounded question answering, and reusable chatbot integration for digital library websites.

# AI Capabilities
## Reusable Chatbot Widget

The project includes a configurable chatbot widget that can be embedded into multiple digital library websites with minimal code changes.

### Widget Features

- Floating chatbot interface
- Responsive design
- Minimize / Maximize support
- Source citation chips
- Direct PDF page navigation
- Configurable API endpoints
- Reusable frontend component
- Plug-and-play integration
* General knowledge fallback for out-of-context questions
* Clickable document source references
* Configurable widget for external library websites

## Objectives

* Build an intelligent document retrieval and question-answering system.
* Enable semantic search over uploaded documents.
* Generate answers grounded in document content.
* Support multiple document formats.
* Reduce hallucinations through retrieval-based generation.
* Provide a secure and fully offline AI solution.


## Features

### User Features

* Secure user authentication
* Natural language question answering
* Source-based responses with citations
* Chat history management
* Responsive user interface

### Administrator Features

* Document upload and management
* Document indexing and re-indexing
* Document deletion
* Real-time indexing status monitoring
* System metrics dashboard
* Security log monitoring

### Document Processing

* PDF document support
* DOCX document support
* TXT and Markdown support
* OCR support for scanned PDFs
* Table extraction from documents
* Automatic text cleaning and preprocessing
* Semantic document chunking

### AI Capabilities

* Retrieval-Augmented Generation (RAG)
* Semantic similarity search
* Context-aware answer generation
* Confidence-based retrieval filtering
* Source citation generation
* Multi-document knowledge retrieval
* Hallucination reduction through document grounding


## Technology Stack

### Backend

* Python
* FastAPI
* SQLite
* SQLAlchemy

### Frontend

* HTML
* CSS
* JavaScript

### AI & NLP

* Ollama
* Llama 3.2 3B
* Sentence Transformers
* LangChain

### Vector Database

* ChromaDB

### Document Processing

* PyMuPDF
* pdfplumber
* python-docx
* Tesseract OCR
* pdf2image


## Models Used

### Embedding Model

**BAAI/bge-base-en-v1.5**

Used for generating vector embeddings of document chunks and user queries, enabling semantic retrieval of relevant information.

### Large Language Model

**Llama 3.2 3B (Ollama)**

Used for generating natural language answers from retrieved document context while maintaining document grounding.

Alternative models such as Phi-3 Mini and TinyLlama can also be configured.

## Running the Project

### Backend

```bash
cd backend
uvicorn app.main:app --reload
```

Backend runs on

```
http://127.0.0.1:8000
```
---

### Admin Dashboard

```
http://127.0.0.1:8000/admin.html
```
---

### Widget Demo

```
http://127.0.0.1:8000/widget-demo.html
```
# Widget Integration

The chatbot widget has been designed as a reusable frontend component.

Files required for integration:

```
frontend/widget/
    nrsc-assistant.js
    nrsc-assistant.css
```

To integrate the widget into another website:

1. Copy the widget folder.
2. Include the CSS and JavaScript files.
3. Configure the backend API endpoints.
4. Initialize the widget.

Only the API configuration needs to be updated for a new deployment. No backend code changes are required.

# Configuration

The widget is configurable through a single configuration object.

Example:

- Backend API URL
- Chat endpoint
- Document endpoint
- Widget title
- Default LLM model

This design minimizes deployment effort when integrating the chatbot into different digital library systems.

## System Workflow

1. User uploads documents.
2. Documents are processed and cleaned.
3. Text is divided into semantic chunks.
4. Embeddings are generated for each chunk.
5. Embeddings are stored in ChromaDB.
6. User submits a question.
7. Relevant chunks are retrieved using semantic search.
8. Retrieved context is passed to the LLM.
9. The LLM generates a grounded response.
10. Relevant source citations are displayed to the user.



## Supported File Formats

* PDF
* DOCX
* TXT

# Project Structure
Knowledge-Expert-System/
│
├── backend/
│   ├── app/
│   │   ├── config/
│   │   ├── models/
│   │   ├── rag/
│   │   ├── routes/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── utils/
│   │
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── css/
│   ├── js/
│   ├── widget/
│   │   ├── nrsc-assistant.js
│   │   └── nrsc-assistant.css
│   │
│   ├── admin.html
│   └── widget-demo.html
│
├── README.md
└── .gitignore

## How to Run

1. Install Python dependencies.
2. Install and start Ollama.
3. Download the required LLM model.
4. Configure environment variables.
5. Start the FastAPI backend.
6. Open the frontend application.
7. Upload documents and begin querying.

