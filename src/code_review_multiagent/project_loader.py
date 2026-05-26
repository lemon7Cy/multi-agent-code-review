from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import PurePosixPath

from fastapi import HTTPException, UploadFile

from .models import ReviewFile

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".php", ".rb", ".cs",
    ".cpp", ".c", ".h", ".hpp", ".kt", ".swift", ".scala", ".sql", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".md", ".dockerfile",
}
SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "dist", "build", ".next", "target", "vendor",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv", "env", ".idea", ".vscode",
}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".docx", ".xlsx", ".zip", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".class", ".jar", ".pyc", ".map", ".lock",
}
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_FILE_BYTES = 300 * 1024
MAX_TOTAL_TEXT_BYTES = 2 * 1024 * 1024
MAX_FILES = 200


def should_include_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip("/")
    if not normalized or normalized.endswith("/"):
        return False
    parts = PurePosixPath(normalized).parts
    if any(part in SKIP_DIRS for part in parts):
        return False
    name = parts[-1]
    suffix = PurePosixPath(name).suffix.lower()
    if name in {"Dockerfile", "Makefile"}:
        return True
    if suffix in SKIP_SUFFIXES:
        return False
    return suffix in CODE_EXTENSIONS or name.startswith(".env")


def extract_review_files_from_zip_bytes(data: bytes) -> tuple[list[ReviewFile], dict[str, int | str]]:
    if len(data) > MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="zip 文件超过 50MB 限制")

    files: list[ReviewFile] = []
    skipped = 0
    total_text_bytes = 0

    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="不是有效的 zip 文件")

    with zf:
        infos = [info for info in zf.infolist() if not info.is_dir()]
        for info in infos:
            path = info.filename.replace("\\", "/").strip("/")
            # 防 Zip Slip：虽然这里不落盘，也保持路径规范。
            if path.startswith("../") or "/../" in path or path.startswith("/"):
                skipped += 1
                continue
            if not should_include_path(path):
                skipped += 1
                continue
            if info.file_size > MAX_FILE_BYTES:
                skipped += 1
                continue
            if len(files) >= MAX_FILES or total_text_bytes >= MAX_TOTAL_TEXT_BYTES:
                skipped += 1
                continue
            raw = zf.read(info)
            if b"\x00" in raw[:2048]:
                skipped += 1
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text = raw.decode("gbk")
                except UnicodeDecodeError:
                    skipped += 1
                    continue
            total_text_bytes += len(text.encode("utf-8"))
            files.append(ReviewFile(path=path, content=text))

    if not files:
        raise HTTPException(status_code=400, detail="zip 中没有找到可审查的代码文件")

    return files, {
        "included_files": len(files),
        "skipped_files": skipped,
        "total_files_in_zip": len(infos),
        "total_text_bytes": total_text_bytes,
        "limits": f"max_files={MAX_FILES}, max_file_bytes={MAX_FILE_BYTES}, max_total_text_bytes={MAX_TOTAL_TEXT_BYTES}",
    }


async def extract_review_files_from_upload(file: UploadFile) -> tuple[list[ReviewFile], dict[str, int | str]]:
    filename = file.filename or "project.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 项目压缩包")
    data = await file.read()
    return extract_review_files_from_zip_bytes(data)
