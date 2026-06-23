# NRSC Documents Knowledge Expert System

The NRSC Documents Knowledge Expert System is an AI-powered document question-answering system developed during my internship at the National Remote Sensing Centre (NRSC), ISRO, Hyderabad.

The project is based on Retrieval-Augmented Generation (RAG) and enables users to upload documents, index their contents, and interact with them using natural language queries. The system retrieves relevant information from uploaded documents and generates grounded responses using a locally hosted Large Language Model (LLM).

The application is designed to work completely offline, ensuring data privacy and secure document processing.


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



## Project Structure

```text
backend/
│
├── app/
│   ├── config/
│   ├── models/
│   ├── rag/
│   ├── routes/
│   ├── services/
│   └── utils/
│
frontend/
│
├── css/
├── js/
└── pages/
```



## How to Run

1. Install Python dependencies.
2. Install and start Ollama.
3. Download the required LLM model.
4. Configure environment variables.
5. Start the FastAPI backend.
6. Open the frontend application.
7. Upload documents and begin querying.

