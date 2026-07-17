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
* Automated document ingestion from configurable source folders
* Duplicate document detection using SHA-256 hashing
* Automatic movement of successfully processed documents to a processed folder

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

## Environment Configuration

The project uses environment variables for configuration.

A sample configuration file, `.env.example`, is included in the repository.

Before running the project:

1. Copy `.env.example`.
2. Rename the copied file to `.env`.
3. Update the configuration values according to your local system.

Only the document folder paths typically need to be changed for a new deployment.

## Document Ingestion Configuration

The document ingestion pipeline uses configurable folders defined in the backend environment file.

Update the following variables in:

**backend/.env**
```env
SOURCE_FOLDER=C:/RAG/source_documents
PROCESSED_FOLDER=C:/RAG/processed_documents
UPLOAD_DIR=backend/uploads
```
### Folder Description

| Folder |                 | Purpose |
| SOURCE_FOLDER |          |Place new PDF documents here for processing |
| PROCESSED_FOLDER |       |Successfully indexed documents are moved here |
| UPLOAD_DIR |             |Temporary storage used by the application before indexing |

## Automated Document Workflow

1. Copy PDF documents into the configured `SOURCE_FOLDER`.
2. Run the library processing script.
3. The documents are copied into the application's upload directory.
4. Duplicate documents are automatically detected using SHA-256 hashing.
5. New documents are indexed into ChromaDB.
6. Successfully indexed documents are moved to the configured `PROCESSED_FOLDER` and are removed from the 'SOURCE_FOLDER'.
7. The chatbot can immediately retrieve information from the newly indexed documents.

## System Workflow
1. Administrator places documents in the configured source folder.
2. The library processor scans the source folder.
3. Duplicate documents are identified using SHA-256 hashing.
4. New documents are copied into the application upload directory.
5. Documents are processed and cleaned.
6. Text is divided into semantic chunks.
7. Embeddings are generated.
8. Embeddings are stored in ChromaDB.
9. Successfully indexed documents are moved to the processed folder.
10. Users submit questions.
11. Relevant chunks are retrieved.
12. The LLM generates grounded responses.
13. Source citations are displayed.

## Supported File Formats

* PDF
* DOCX
* TXT

## Project Structure

```text
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
```

## How to Run
### Prerequisites
1. Install the required Python dependencies.
2. Install and start Ollama.
3. Download the required LLM model (e.g., Llama 3.2 3B).
4. Clone the repository.
### Step 1: Configure the Environment
Edit the following file:

**backend/.env**
Configure the required folder paths:
```env
SOURCE_FOLDER=C:/RAG/source_documents
PROCESSED_FOLDER=C:/RAG/processed_documents
UPLOAD_DIR=backend/uploads
```
Create the `SOURCE_FOLDER` and `PROCESSED_FOLDER` directories if they do not already exist.

### Step 2: Start the Backend Server

```bash
cd backend
uvicorn app.main:app --reload
```
The backend will be available at:

```text
http://127.0.0.1:8000
```
### Step 3: Process Library Documents
Copy the PDF files you want to index into the configured `SOURCE_FOLDER`.
Run the document processing script:
```bash
python library_processor.py
```
The script will:

- Detect all PDF files in the source folder.
- Skip duplicate documents using SHA-256 hashing.
- Copy new documents into the upload directory.
- Process and index the documents into ChromaDB.
- Move successfully indexed documents to the processed folder.

### Step 4: Launch the Frontend

Open one of the following pages in your browser:

**Admin Dashboard**

```text
http://127.0.0.1:8000/admin.html
```

**Widget Demo**

```text
http://127.0.0.1:8000/widget-demo.html
```
You can now upload documents through the admin interface or interact with the chatbot using the widget.
