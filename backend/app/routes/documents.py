import gc
import logging
import mimetypes
import re
import time
from pathlib import Path
#Added imports for time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.security import (
    get_current_user,
    require_admin,
)
from app.config.settings import get_settings
from app.database.session import (
    SessionLocal,
    get_db,
)
from app.models.models import (
    Document,
    User,
)
from app.rag.vector_store import (
    get_vector_store,
)
from app.schemas.schemas import (
    DocumentOut,
)
from app.services.audit_service import (
    audit,
)
from app.services.document_processor import (
    extract_document,
    sha256_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents"])
settings = get_settings()
#Added function for time zone
def indian_time():
    return datetime.now(
        ZoneInfo("Asia/Kolkata")
    )

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_FILE_SIZE = 100 * 1024 * 1024

# Thread-safe cancellation checklist monitoring processing state changes
_CANCELLED_INDEX_IDS: set[int] = set()


# =========================================================
# INDEX CANCELLATION (FORCE DELETE DURING PROCESSING)
# =========================================================

def mark_index_cancelled(document_id: int) -> None:
    _CANCELLED_INDEX_IDS.add(document_id)


def clear_index_cancelled(document_id: int) -> None:
    _CANCELLED_INDEX_IDS.discard(document_id)


def indexing_was_cancelled(document_id: int) -> bool:
    return document_id in _CANCELLED_INDEX_IDS


def should_abort_indexing(document_id: int, db: Session) -> bool:
    if indexing_was_cancelled(document_id):
        return True
    return db.query(Document).filter(Document.id == document_id).first() is None


# =========================================================
# SAFE FILE DELETE (WINDOWS FILE LOCKING)
# =========================================================

def safe_unlink(file_path: Path, retries: int = 8, delay_seconds: float = 0.5) -> bool:
    """Remove a file with retries for Windows indexing locks."""
    if not file_path.exists():
        return True

    for attempt in range(retries):
        try:
            file_path.unlink()
            return True
        except PermissionError:
            gc.collect()
            if attempt < retries - 1:
                time.sleep(delay_seconds * (attempt + 1))
        except OSError:
            if attempt < retries - 1:
                time.sleep(delay_seconds * (attempt + 1))

    return not file_path.exists()


def force_remove_upload_file(file_path: Path, document_id: int) -> tuple[bool, str | None]:
    """Delete upload file with extended retries; rename if still locked."""
    if not file_path.exists():
        return True, None

    if safe_unlink(file_path, retries=12, delay_seconds=0.75):
        return True, None

    quarantine = file_path.with_name(f"{file_path.name}.deleted.{document_id}")

    try:
        if file_path.exists():
            file_path.rename(quarantine)
        if safe_unlink(quarantine, retries=8, delay_seconds=0.75):
            return True, None
    except OSError as exc:
        logger.warning(
            "Could not rename locked upload for document %s: %s",
            document_id,
            exc,
        )

    if not file_path.exists() and not quarantine.exists():
        return True, None

    if quarantine.exists() and not file_path.exists():
        return True, (
            "Document removed; a temporary file may be "
            "cleaned up after indexing stops."
        )

    return False, None


def content_disposition(disposition: str, filename: str) -> str:
    safe_name = filename.replace("\\", "_").replace('"', "_").strip() or "document"
    return f'{disposition}; filename="{safe_name}"'


# =========================================================
# SAFE FILE NAME
# =========================================================

def safe_stored_filename(original_filename: str, upload_dir: str) -> str:
    original = Path(original_filename or "document").name
    stem = Path(original).stem
    suffix = Path(original).suffix.lower()

    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "document"
    candidate = f"{safe_stem}{suffix}"
    destination = Path(upload_dir) / candidate

    counter = 1
    while destination.exists():
        candidate = f"{safe_stem}_{counter}{suffix}"
        destination = Path(upload_dir) / candidate
        counter += 1

    return candidate


# =========================================================
# BACKGROUND INDEXING
# =========================================================

def index_document(document_id: int) -> None:
    # FIXED: Handled isolated database scope correctly inside background worker process boundaries
    db = SessionLocal()
    vector_store = get_vector_store()

    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
    #Added return False
        if not doc or should_abort_indexing(document_id, db):
            return False

        logger.info(f"Starting indexing for document {doc.id}: {doc.filename}")
        doc.status = "Processing"
        db.commit()

        if should_abort_indexing(document_id, db):
            return
#Added changed with actual storage location
        path = Path(settings.upload_dir) / doc.stored_filename         
        if not path.exists():
            doc.status = "Failed"
            doc.error_message = "Uploaded file not found."
            db.commit()
    #Added false to return stmt
            return False

        # Core file parsing
        result = extract_document(path, doc.filename, doc.document_type)
    #Added to print
        print(f"Extracted {len(result.chunks)} chunks")
        if should_abort_indexing(document_id, db):
            return

        if not result.chunks:
            doc.status = "Failed"
            doc.error_message = "No searchable content found."
            db.commit()
    #Added false
            return False

        # FIXED: Clean up vector database elements *before* writing new data to prevent duplicates
        try:
            vector_store.delete_document(document_id)
        except Exception:
            pass

        if should_abort_indexing(document_id, db):
    #Added false
            return False

        # Perform the vector write operations
        vector_store.add_document_chunks(document_id, result.chunks)
#Added to print
        print("Stored chunks in ChromaDB")
        # FIXED: Re-verify database record existence right after vector extraction pipeline executions
        if should_abort_indexing(document_id, db):
            try:
                vector_store.delete_document(document_id)
            except Exception:
                pass
            logger.info(f"Indexing aborted mid-process for document {document_id}; rolled back vector chunks safely.")
            return

        doc.status = "Indexed"
    #Added the processed time
        doc.processed_at = indian_time()
    #Added to see indexing complteted
        print("Indexing Complete")
        doc.chunk_count = len(result.chunks)
        doc.page_count = result.page_count
        doc.table_count = result.table_count
        doc.error_message = None
        db.commit()
        
        logger.info(f"Successfully indexed document {document_id}")
        #Added true
        return True

    except Exception as exc:
        logger.exception(f"Indexing failed for document {document_id}: {str(exc)}")
        try:
            db.rollback()
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc and not indexing_was_cancelled(document_id):
                doc.status = "Failed"
                doc.error_message = str(exc)
                db.commit()
        except Exception:
            db.rollback()
    #Added false after exception
        return False
    finally:
        clear_index_cancelled(document_id)
        db.close()


# =========================================================
# UPLOAD
# =========================================================

@router.post("/upload", response_model=list[DocumentOut])
async def upload_documents(
    background_tasks: BackgroundTasks,
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    created = []
    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)

    for file in files:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Invalid filename.")

        suffix = Path(file.filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

        stored_filename = safe_stored_filename(file.filename, settings.upload_dir)
        destination = upload_path / stored_filename
        size = 0

        try:
            with destination.open("wb") as out:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_FILE_SIZE:
                        destination.unlink(missing_ok=True)
                        raise HTTPException(status_code=400, detail="File exceeds 100MB limit.")
                    out.write(chunk)
        except Exception as exc:
            destination.unlink(missing_ok=True)
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(status_code=500, detail=f"File stream upload failed: {str(exc)}")
        finally:
            await file.close()

        content_hash = sha256_file(destination)
        duplicate = db.query(Document).filter(Document.content_hash == content_hash).first()

        if duplicate:
            destination.unlink(missing_ok=True)
            created.append(duplicate)
            continue
#Added document location
        doc = Document(
            filename=file.filename or destination.name,
            stored_filename=stored_filename,
            storage_path=str(destination),
            content_hash=content_hash,
            document_type=suffix.lstrip("."),
            size_bytes=size,
            status="Uploaded",
            uploaded_by=current_user.id,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # FIXED: Pass only primary key type signatures to asynchronous processing background routines
        background_tasks.add_task(index_document, doc.id)

        audit(
            db,
            "UPLOAD_DOCUMENT",
            file.filename,
            current_user,
            request.client.host if request.client else None,
        )
        created.append(doc)

    return created


# =========================================================
# USER SOURCE LOOKUP (CHAT CITATIONS)
# =========================================================

def _find_document_by_name(db: Session, name: str) -> Document | None:
    cleaned = (name or "").strip()
    if not cleaned:
        return None

    doc = db.query(Document).filter(Document.filename == cleaned).first()
    if doc:
        return doc

    return db.query(Document).filter(Document.filename.ilike(f"%{cleaned}%")).first()


@router.get("/documents/search")
async def search_document_snippets(
    q: str = Query(..., min_length=1),
    page: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = _find_document_by_name(db, q)
    if not doc:
        return {"document_id": None, "filename": q.strip(), "snippets": []}

    snippets = get_vector_store().get_document_snippets(doc.id, limit=100)

    if page is not None and str(page).strip() not in {"", "-"}:
        page_value = str(page).strip()
        filtered = [item for item in snippets if str(item.get("page", "")).strip() == page_value]
        if filtered:
            snippets = filtered

    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "snippets": snippets[:10],
    }


@router.get("/documents/view/{document_id}")
async def view_document_for_user(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
#Added changes in the file path
    file_path = Path(settings.processed_folder) / doc.stored_filename

#Added changed file path-1
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    media_type, _ = mimetypes.guess_type(str(file_path))
    if not media_type:
        media_type = "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=doc.filename,
       # headers={"Content-Disposition": content_disposition("inline", doc.filename)},
    )
#Added to open files
@router.get("/public/document/{document_id}")
async def public_view_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()

    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )
#Added changed the path-2
    print("========== PUBLIC OPEN ==========")
    print("Document ID :", doc.id)
    print("Filename    :", doc.filename)
    print("StoragePath :", doc.storage_path)
    print("Stored Name :", doc.stored_filename)
    print("================================")
    
    file_path = Path(settings.processed_folder) / doc.stored_filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    media_type, _ = mimetypes.guess_type(str(file_path))

    if not media_type:
        media_type = "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=doc.filename,
    )

# =========================================================
# LIST DOCUMENTS
# =========================================================

@router.get("/documents", response_model=list[DocumentOut])
async def documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return db.query(Document).order_by(Document.created_at.desc()).all()


# =========================================================
# OPEN / DOWNLOAD DOCUMENT
# =========================================================

@router.get("/download/{document_id}")
async def download_document(
    document_id: int,
    download: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
#Added chenged path-3
    file_path = Path(settings.processed_folder) / doc.stored_filename

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    media_type, _ = mimetypes.guess_type(str(file_path))
    if not media_type:
        media_type = "application/octet-stream"

    disposition = "attachment" if download else "inline"
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=doc.filename,
        headers={"Content-Disposition": content_disposition(disposition, doc.filename)},
    )


# =========================================================
# DELETE DOCUMENT
# =========================================================

@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
#Added changed path-4
    file_path = Path(settings.processed_folder) / doc.stored_filename
    filename = doc.filename
    was_processing = doc.status == "Processing"

    # Set cancellation signal flags immediately to block mid-flight index tasks
    mark_index_cancelled(document_id)

    try:
        # Step 1: Force remove matching collection indices inside ChromaDB
        try:
            vector_store = get_vector_store()
            vector_store.delete_document(doc.id)
        except Exception as exc:
            logger.warning(f"Vector cleanup skipped for document {doc.id}: {str(exc)}")

        # Step 2: Delete standard relational database rows
        db.delete(doc)
        db.commit()

        # Step 3: Run file cancellation cleanups safely on the Windows disk
        file_removed, file_warning = force_remove_upload_file(file_path, document_id)

        audit(
            db,
            "DELETE_DOCUMENT",
            f"Deleted: {filename}",
            current_user,
            request.client.host if request.client else None,
        )

        message = "Document deleted successfully"
        if was_processing:
            message = "Document deleted successfully (indexing was cancelled)"

        if file_warning:
            message = f"{message}. {file_warning}"

        if not file_removed:
            logger.warning(f"Document {document_id} cleared from DB but physical file remains locked: {file_path}")
            message = f"{message} The upload file is still in use and will be automatically cleared when processing finishes."

        return {
            "success": True,
            "message": message,
            "file_removed": file_removed,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception(f"Delete failed: {str(exc)}")
        raise HTTPException(status_code=500, detail="Failed to delete document")
    