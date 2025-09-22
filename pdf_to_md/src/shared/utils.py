"""Shared utility functions"""

import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

def generate_doc_id(content: bytes) -> str:
    """Generate document ID from content"""
    return hashlib.md5(content).hexdigest()

def generate_task_id(prefix: str = "task") -> str:
    """Generate unique task ID"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def format_duration(seconds: float) -> str:
    """Format duration in human readable format"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"

def safe_filename(filename: str) -> str:
    """Make filename safe for filesystem"""
    # Remove or replace unsafe characters
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        max_name_length = 255 - len(ext) - 1 if ext else 255
        filename = name[:max_name_length] + ('.' + ext if ext else '')
    
    return filename

def ensure_directory(path: Path) -> Path:
    """Ensure directory exists and return path"""
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_file_extension(filename: str) -> str:
    """Get file extension from filename"""
    return Path(filename).suffix.lower()

def is_pdf_file(filename: str) -> bool:
    """Check if file is PDF by extension"""
    return get_file_extension(filename) == '.pdf'

def validate_file_size(content: bytes, max_size_mb: int) -> bool:
    """Validate file size"""
    max_size_bytes = max_size_mb * 1024 * 1024
    return len(content) <= max_size_bytes

def create_temp_file(content: bytes, suffix: str = ".tmp") -> Path:
    """Create temporary file with content"""
    import tempfile
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_file.write(content)
    temp_file.close()
    return Path(temp_file.name)

def cleanup_temp_file(file_path: Path) -> bool:
    """Cleanup temporary file"""
    try:
        if file_path.exists():
            file_path.unlink()
        return True
    except Exception:
        return False

def merge_dicts(*dicts: Dict[str, Any]) -> Dict[str, Any]:
    """Merge multiple dictionaries"""
    result = {}
    for d in dicts:
        result.update(d)
    return result

def filter_none_values(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove None values from dictionary"""
    return {k: v for k, v in data.items() if v is not None}

def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate string to maximum length"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
