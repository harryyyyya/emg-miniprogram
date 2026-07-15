"""
routers/upload.py - EMG 训练数据分片上传接口
  POST /upload/chunk   接收单个分片（multipart/form-data）
  POST /upload/merge   所有分片上传完毕后合并
"""
import json
import os
import struct
import zlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from models import EmgCollectionSession, get_db, TrainingSession, User
from deps import get_current_user

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR   = Path("uploads")
CHUNK_DIR    = UPLOAD_DIR / "chunks"
EMG_DIR      = UPLOAD_DIR / "emg"

# 确保目录存在
CHUNK_DIR.mkdir(parents=True, exist_ok=True)
EMG_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────
# 分片接收
# ──────────────────────────────────────────────
@router.post("/chunk")
async def upload_chunk(
    file:        UploadFile = File(...),
    session_id:  str        = Form(...),
    chunk_index: str        = Form(...),
    db:          Session    = Depends(get_db),
    current_user: User      = Depends(get_current_user),
):
    idx = int(chunk_index)
    session_dir = CHUNK_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    chunk_path = session_dir / f"chunk_{idx:05d}.dat"
    content = await file.read()
    chunk_path.write_bytes(content)

    return {"message": "分片接收成功", "chunk_index": idx, "size": len(content)}


# ──────────────────────────────────────────────
# 合并分片
# ──────────────────────────────────────────────
class MergeIn:
    def __init__(self, session_id: str = Form(...), total_chunks: str = Form(...)):
        self.session_id   = session_id
        self.total_chunks = int(total_chunks)

from pydantic import BaseModel

class MergeBody(BaseModel):
    session_id:   str
    total_chunks: int
    gesture_name: str = ""


@router.post("/merge")
def merge_chunks(
    body:         MergeBody,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    session_dir = CHUNK_DIR / body.session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="会话分片不存在，请重新上传")

    # 按序号收集分片
    chunks = sorted(session_dir.glob("chunk_*.dat"), key=lambda p: int(p.stem.split("_")[1]))
    if len(chunks) != body.total_chunks:
        raise HTTPException(
            status_code=400,
            detail=f"分片数量不匹配：期望 {body.total_chunks}，实际 {len(chunks)}"
        )

    # 合并写入 emg 目录
    out_path = EMG_DIR / f"{body.session_id}.dat"
    with open(out_path, "wb") as out:
        for chunk_file in chunks:
            out.write(chunk_file.read_bytes())

    # 清理临时分片
    for chunk_file in chunks:
        chunk_file.unlink(missing_ok=True)
    try:
        session_dir.rmdir()
    except OSError:
        pass

    # 解析 EMG 统计信息（8 通道 int16）
    raw      = out_path.read_bytes()
    stats    = _parse_emg_stats(raw)
    preview  = _parse_preview_from_raw(raw)

    # 记录到数据库
    record = TrainingSession(
        session_id   = body.session_id,
        user_id      = current_user.id,
        gesture_name = body.gesture_name,
        file_path    = str(out_path),
        total_chunks = body.total_chunks,
    )
    db.add(record)
    _upsert_emg_collection_session(
        db,
        user_id=current_user.id,
        session_id=body.session_id,
        gesture_name=body.gesture_name,
        file_path=str(out_path),
        sample_count=stats["sample_count"],
        batch_count=body.total_chunks,
        rms_value=stats["rms"],
        preview_json=json.dumps(preview, ensure_ascii=False),
    )
    db.commit()

    return {
        "message":      "合并成功",
        "session_id":   body.session_id,
        "file_size":    len(raw),
        "sample_count": stats["sample_count"],
        "rms":          stats["rms"],
    }


def _parse_emg_stats(raw: bytes) -> dict:
    """简单解析 8 通道 int16 EMG 数据，返回样本数和 RMS"""
    CHANNELS = 8
    BYTES_PER_SAMPLE = CHANNELS * 2
    n = len(raw) // BYTES_PER_SAMPLE
    if n == 0:
        return {"sample_count": 0, "rms": 0.0}
    total_sq = 0.0
    for i in range(n):
        for ch in range(CHANNELS):
            val = struct.unpack_from("<h", raw, i * BYTES_PER_SAMPLE + ch * 2)[0]
            total_sq += val * val
    rms = (total_sq / (n * CHANNELS)) ** 0.5
    return {"sample_count": n, "rms": round(rms, 2)}


def _parse_preview_from_raw(raw: bytes, limit: int = 24) -> list[list[int]]:
    CHANNELS = 8
    BYTES_PER_SAMPLE = CHANNELS * 2
    n = len(raw) // BYTES_PER_SAMPLE
    preview: list[list[int]] = []
    for i in range(min(n, limit)):
        row: list[int] = []
        for ch in range(CHANNELS):
            row.append(struct.unpack_from("<h", raw, i * BYTES_PER_SAMPLE + ch * 2)[0])
        preview.append(row)
    return preview


def _upsert_emg_collection_session(
    db: Session,
    *,
    user_id: int,
    session_id: str,
    gesture_name: str,
    file_path: str,
    sample_count: int,
    batch_count: int,
    rms_value: float,
    preview_json: str = "[]",
) -> EmgCollectionSession:
    record = db.query(EmgCollectionSession).filter(EmgCollectionSession.session_id == session_id).first()
    if not record:
        record = EmgCollectionSession(
            session_id=session_id,
            user_id=user_id,
            transport="ble",
            source="ble",
        )
        db.add(record)

    record.user_id = user_id
    record.transport = "ble"
    record.source = "ble"
    record.hardware_id = ""
    record.gesture_name = gesture_name
    record.sample_rate_hz = 0
    record.channel_count = 8
    record.batch_count = batch_count
    record.total_samples = sample_count
    record.rms_value = rms_value
    record.file_path = file_path
    record.preview_json = preview_json
    record.is_completed = True
    return record


# ──────────────────────────────────────────────
# 图片上传（论坛用）
# ──────────────────────────────────────────────
IMAGE_DIR = UPLOAD_DIR / "images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_SUFFIX = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


@router.post("/image")
async def upload_image(
    file:         UploadFile = File(...),
    current_user: User       = Depends(get_current_user),
):
    suffix = Path(file.filename or "img.jpg").suffix.lower()
    if suffix not in ALLOWED_SUFFIX:
        raise HTTPException(status_code=400, detail="不支持的图片格式")

    import uuid
    filename = f"{uuid.uuid4().hex}{suffix}"
    dest = IMAGE_DIR / filename
    dest.write_bytes(await file.read())

    # 返回可访问的 URL（需配合 main.py 中的 StaticFiles 挂载）
    return {"url": f"/static/images/{filename}"}
