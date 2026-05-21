# NRSC Documents Knowledge Expert System

Offline secure RAG-based AI knowledge assistant with FastAPI, vanilla HTML/CSS/JavaScript, SQLite, ChromaDB, LangChain chunking, sentence-transformer embeddings, and Ollama local LLM generation.

## Features

- JWT login with administrator and user roles
- Admin dashboard, document upload, file management, re-indexing, and security logs
- User dashboard, AI question answering, source citations, and chat history
- PDF, DOCX, TXT, and Markdown document ingestion
- OCR fallback for scanned PDFs using `pytesseract` and `pdf2image`
- Table extraction using `pdfplumber`
- Recursive chunking with chunk size `1000` and overlap `200`
- Persistent ChromaDB vector store
- Embedding model: `all-MiniLM-L6-v2`
- Local Ollama model support: `phi3:mini` and `tinyllama`
- Fully offline usage after packages, embedding model, and Ollama models are installed locally

## Default Credentials

Administrator:

```text
username: admin
password: admin123
