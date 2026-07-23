"""
Forum router.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from deps import get_current_user, get_current_user_optional
from models import ForumComment, ForumPost, PostLike, User, get_db

router = APIRouter(prefix="/forum", tags=["forum"])

IMAGE_DIR = Path("uploads/images")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _time_ago(dt: datetime) -> str:
    now = datetime.utcnow()
    delta = int((now - dt).total_seconds())
    if delta < 60:
        return "刚刚"
    if delta < 3600:
        return f"{delta // 60}分钟前"
    if delta < 86400:
        return f"{delta // 3600}小时前"
    return f"{delta // 86400}天前"


def _post_dict(post: ForumPost, current_user: User | None) -> dict:
    uid = current_user.id if current_user else -1
    liked = any(lk.user_id == uid for lk in post.likes)
    return {
        "id": post.id,
        "author_id": post.user_id,
        "user_id": post.user_id,
        "author_name": post.author.name,
        "author_avatar": post.author.avatar_url or "/assets/icons/default_avatar.png",
        "created_at": _time_ago(post.created_at),
        "title": (post.content or "")[:24],
        "content": post.content,
        "parent_id": None,
        "pinned": False,
        "hidden": False,
        "image_urls": json.loads(post.image_urls) if post.image_urls else [],
        "like_count": post.like_count,
        "comment_count": post.comment_count,
        "liked": liked,
        "can_delete": uid == post.user_id,
    }


def _reply_dict(comment: ForumComment, current_user: User | None = None) -> dict:
    can_delete = bool(current_user and current_user.id == comment.user_id)
    return {
        "id": comment.id,
        "author_id": comment.user_id,
        "author_name": comment.author.name,
        "author_avatar": comment.author.avatar_url or "/assets/icons/default_avatar.png",
        "created_at": _time_ago(comment.created_at),
        "content": comment.content,
        "parent_id": comment.parent_id,
        "reply_to_user_name": comment.reply_to_user.name if comment.reply_to_user else "",
        "can_delete": can_delete,
    }


def _comment_dict(comment: ForumComment, current_user: User | None = None) -> dict:
    replies = sorted(comment.replies, key=lambda item: item.created_at)
    can_delete = bool(current_user and current_user.id == comment.user_id)
    return {
        "id": comment.id,
        "author_id": comment.user_id,
        "author_name": comment.author.name,
        "author_avatar": comment.author.avatar_url or "/assets/icons/default_avatar.png",
        "created_at": _time_ago(comment.created_at),
        "content": comment.content,
        "reply_count": len(replies),
        "replies": [_reply_dict(reply, current_user) for reply in replies],
        "can_delete": can_delete,
    }


def _delete_comment_tree(db: Session, post_id: int, root_comment_ids: list[int]) -> int:
    """Delete a comment subtree from leaves to root."""
    roots = [comment_id for comment_id in root_comment_ids if comment_id is not None]
    if not roots:
        return 0

    deleted_count = 0
    levels: list[list[int]] = []
    frontier = roots

    while frontier:
        child_ids = [
            row[0]
            for row in db.query(ForumComment.id)
            .filter(ForumComment.post_id == post_id, ForumComment.parent_id.in_(frontier))
            .all()
        ]
        if not child_ids:
            break
        levels.append(child_ids)
        frontier = child_ids

    for level_ids in reversed(levels):
        deleted_count += (
            db.query(ForumComment)
            .filter(ForumComment.post_id == post_id, ForumComment.id.in_(level_ids))
            .delete(synchronize_session=False)
        )

    deleted_count += (
        db.query(ForumComment)
        .filter(ForumComment.post_id == post_id, ForumComment.id.in_(roots))
        .delete(synchronize_session=False)
    )
    return deleted_count


class PostIn(BaseModel):
    content: str
    image_urls: list[str] = []


class CommentIn(BaseModel):
    content: str
    parent_id: int | None = None


class LegacyLikeIn(BaseModel):
    post_id: int


class LegacyCommentIn(BaseModel):
    post_id: int
    content: str
    parent_id: int | None = None


class AdminPostUpdateIn(BaseModel):
    pinned: bool | None = None
    hidden: bool | None = None
    content: str | None = Field(default=None, max_length=1000)


@router.get("/posts")
def list_posts(
    page: int = 1,
    size: int = 15,
    search: str = "",
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    offset = (page - 1) * size
    query = db.query(ForumPost).options(selectinload(ForumPost.author), selectinload(ForumPost.likes))
    keyword = (search or "").strip()
    if keyword:
        query = query.filter(ForumPost.content.contains(keyword))

    posts = (
        query
        .order_by(ForumPost.created_at.desc())
        .offset(offset)
        .limit(size)
        .all()
    )
    return {"posts": [_post_dict(post, current_user) for post in posts]}


@router.post("/posts")
def create_post(
    body: PostIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="内容不能为空")

    post = ForumPost(
        user_id=current_user.id,
        content=content,
        image_urls=json.dumps(body.image_urls, ensure_ascii=False),
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return {"post_id": post.id, "message": "发布成功"}


@router.post("/posts/{post_id}/like")
def like_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(ForumPost).filter(ForumPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")

    like = db.query(PostLike).filter(
        PostLike.post_id == post_id,
        PostLike.user_id == current_user.id,
    ).first()

    if like:
        db.delete(like)
        post.like_count = max(0, post.like_count - 1)
        liked = False
    else:
        db.add(PostLike(post_id=post_id, user_id=current_user.id))
        post.like_count += 1
        liked = True

    db.commit()
    return {"liked": liked, "like_count": post.like_count}


@router.post("/like")
def legacy_like_post(
    body: LegacyLikeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return like_post(body.post_id, db, current_user)


@router.put("/posts/{post_id}")
def update_post_for_web(
    post_id: int,
    body: AdminPostUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(ForumPost).filter(ForumPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    if post.user_id != current_user.id and (current_user.role or "user") != "admin":
        raise HTTPException(status_code=403, detail="无权修改该帖子")
    if body.content is not None and body.content.strip():
        post.content = body.content.strip()
    db.commit()
    db.refresh(post)
    return _post_dict(post, current_user)


@router.delete("/posts/{post_id}")
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(ForumPost).filter(ForumPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")

    if post.user_id != current_user.id and (current_user.role or "user") != "admin":
        raise HTTPException(status_code=403, detail="只能删除自己发布的帖子")

    db.query(PostLike).filter(PostLike.post_id == post_id).delete(synchronize_session=False)
    root_comment_ids = [
        row[0]
        for row in db.query(ForumComment.id)
        .filter(ForumComment.post_id == post_id, ForumComment.parent_id.is_(None))
        .all()
    ]
    _delete_comment_tree(db, post_id, root_comment_ids)
    db.delete(post)
    db.commit()
    return {"message": "帖子已删除"}


@router.get("/posts/{post_id}/comments")
def list_comments(
    post_id: int,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    post = db.query(ForumPost).filter(ForumPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")

    offset = (page - 1) * size
    comments = (
        db.query(ForumComment)
        .options(
            selectinload(ForumComment.author),
            selectinload(ForumComment.replies).selectinload(ForumComment.author),
            selectinload(ForumComment.replies).selectinload(ForumComment.reply_to_user),
        )
        .filter(ForumComment.post_id == post_id, ForumComment.parent_id.is_(None))
        .order_by(ForumComment.created_at.asc())
        .offset(offset)
        .limit(size)
        .all()
    )
    total = db.query(ForumComment).filter(ForumComment.post_id == post_id).count()
    return {
        "comments": [_comment_dict(comment, current_user) for comment in comments],
        "total": total,
    }


@router.get("/comments")
def legacy_list_comments(
    post_id: int,
    page: int = 1,
    pageSize: int = 20,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    return list_comments(post_id, page, pageSize, db, current_user)


@router.post("/posts/{post_id}/comments")
def add_comment(
    post_id: int,
    body: CommentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(ForumPost).filter(ForumPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="评论内容不能为空")

    parent = None
    parent_id = body.parent_id
    reply_to_user_id = None
    if body.parent_id is not None:
        parent = db.query(ForumComment).filter(ForumComment.id == body.parent_id).first()
        if not parent or parent.post_id != post_id:
            raise HTTPException(status_code=404, detail="回复的评论不存在")
        if parent.parent_id is not None:
            parent_id = parent.parent_id
        reply_to_user_id = parent.user_id

    comment = ForumComment(
        post_id=post_id,
        user_id=current_user.id,
        parent_id=parent_id,
        reply_to_user_id=reply_to_user_id,
        content=content,
    )
    db.add(comment)
    post.comment_count += 1
    db.commit()
    db.refresh(comment)
    return {"comment_id": comment.id, "message": "评论成功"}


@router.post("/comments")
def legacy_add_comment(
    body: LegacyCommentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return add_comment(
        body.post_id,
        CommentIn(content=body.content, parent_id=body.parent_id),
        db,
        current_user,
    )


@router.delete("/posts/{post_id}/comments/{comment_id}")
def delete_comment(
    post_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(ForumPost).filter(ForumPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")

    comment = db.query(ForumComment).filter(
        ForumComment.id == comment_id,
        ForumComment.post_id == post_id,
    ).first()
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")

    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能删除自己发布的评论")

    deleted_count = _delete_comment_tree(db, post_id, [comment_id])

    post.comment_count = max(0, post.comment_count - deleted_count)
    db.commit()
    return {"message": "评论已删除", "deleted_count": deleted_count}


@router.post("/upload/image")
async def upload_forum_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    suffix = Path(file.filename or "img.jpg").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(status_code=400, detail="不支持的图片格式")

    filename = f"{uuid.uuid4().hex}{suffix}"
    (IMAGE_DIR / filename).write_bytes(await file.read())
    return {"url": f"/static/images/{filename}", "image_url": f"/static/images/{filename}"}
