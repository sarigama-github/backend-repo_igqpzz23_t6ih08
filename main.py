import os
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime

from database import create_document, get_documents, db
from schemas import Video

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure uploads directory exists
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Serve uploaded files statically (supports range requests for video streaming)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response


class VideoOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    filename: str
    url: str
    content_type: str
    size_bytes: Optional[int] = None
    created_at: Optional[str] = None


@app.post("/api/videos", response_model=VideoOut)
async def upload_video(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...)
):
    if not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Only video files are allowed")

    # Generate a safe unique filename
    base_name = os.path.splitext(os.path.basename(file.filename))[0]
    ext = os.path.splitext(file.filename)[1]
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    safe_base = "".join(c for c in base_name if c.isalnum() or c in ("-", "_"))[:50]
    final_name = f"{safe_base or 'video'}_{timestamp}{ext}"
    file_path = os.path.join(UPLOAD_DIR, final_name)

    # Save file to disk
    with open(file_path, "wb") as out_file:
        out_file.write(await file.read())

    size_bytes = os.path.getsize(file_path)

    # Save metadata to database
    video_doc = Video(
        title=title,
        description=description,
        filename=final_name,
        content_type=file.content_type,
        size_bytes=size_bytes,
    )
    inserted_id = create_document("video", video_doc)

    base_url = os.getenv("PUBLIC_BACKEND_URL") or ""  # Optional external URL
    url_path = f"/uploads/{final_name}"
    url = f"{base_url}{url_path}" if base_url else url_path

    return VideoOut(
        id=inserted_id,
        title=title,
        description=description,
        filename=final_name,
        url=url,
        content_type=file.content_type,
        size_bytes=size_bytes,
        created_at=datetime.utcnow().isoformat()
    )


@app.get("/api/videos", response_model=List[VideoOut])
def list_videos():
    docs = get_documents("video", {}, limit=100)
    results: List[VideoOut] = []
    for d in docs:
        _id = str(d.get("_id"))
        filename = d.get("filename")
        base_url = os.getenv("PUBLIC_BACKEND_URL") or ""
        url_path = f"/uploads/{filename}"
        url = f"{base_url}{url_path}" if base_url else url_path
        created_at = d.get("created_at")
        created_at_str = created_at.isoformat() if hasattr(created_at, "isoformat") else None
        results.append(VideoOut(
            id=_id,
            title=d.get("title", "Untitled"),
            description=d.get("description"),
            filename=filename,
            url=url,
            content_type=d.get("content_type", "video/mp4"),
            size_bytes=d.get("size_bytes"),
            created_at=created_at_str
        ))
    return results


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
