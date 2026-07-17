#Read source_folder->Find all PDF'S-> Call existing RAG Pipeline-> Send all files to Processed_folder
from pathlib import Path
import shutil
from app.database.session import SessionLocal
from app.models.models import Document
from app.routes.documents import index_document
from app.services.document_processor import sha256_file
from app.config.settings import get_settings

settings = get_settings()

def get_source_documents():
    source = Path(settings.source_folder)

    pdfs = [
        file
        for file in source.iterdir()
        if file.is_file() and file.suffix.lower() == ".pdf"
    ]

    return pdfs


def process_library():

    pdfs = get_source_documents()

    print(f"Processing {len(pdfs)} PDF(s)...")

    if not pdfs:
        print("No PDFs found.")
        return

    for pdf in pdfs:

        print(f"Processing: {pdf.name}")
        # Added Copy PDF to uploads folder

        destination = Path(settings.upload_dir) / pdf.name

        shutil.copy2(pdf, destination)

        print(f"Copied -> {destination}")

        db = SessionLocal()

        try:

            content_hash = sha256_file(destination)

            duplicate = (
                db.query(Document)
                .filter(Document.content_hash == content_hash)
                .first()
            )

            if duplicate:

                print(f"Skipping duplicate : {pdf.name}")

                destination.unlink(missing_ok=True)

                processed = Path(settings.processed_folder) / pdf.name

                if not processed.exists():
                    shutil.move(pdf, processed)
                    print("Moved existing duplicate to Processed")

                else:
                    pdf.unlink()
                    print("Duplicate already exists in Processed. Deleted from Source.")

                continue

            print("Creating database record...")

            document = Document(
                filename=pdf.name,
                stored_filename=destination.name,
                content_hash=content_hash,
                document_type=pdf.suffix.lower().replace(".", ""),
                size_bytes=pdf.stat().st_size,
                status="Uploaded",
            )

            db.add(document)
            db.commit()
            db.refresh(document)

            print(f"Created Document ID : {document.id}")
# Move file to Processed only after successful indexing.
# If indexing fails, keep the original PDF in Source.
            success = index_document(document.id)

            # Reload document from database
            db.refresh(document)

            if document.status != "Indexed":
                print(f"Indexing failed for {pdf.name}")
                print("Leaving file in Source Folder")
                if destination.exists():
                     destination.unlink()
                continue

            if success:

                print("Indexing Complete")

                processed = (
                    Path(settings.processed_folder)
                    / pdf.name
                )

                if processed.exists():
                    processed.unlink()   

                shutil.move(
                    destination,
                    processed,
                )

                document.storage_path = str(processed)
                document.status = "Processed"
                db.commit()
                db.refresh(document)

                if pdf.exists():
                    pdf.unlink()

                print("Removed from Source Folder")
                print(f"Moved to : {processed}")

            else:

                print("Indexing Failed")
                print("File kept in Source Folder")

        finally:
            db.close()
if __name__ == "__main__":
    process_library()