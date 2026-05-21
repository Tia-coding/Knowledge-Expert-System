"""
Input validation and security validators for NRSC system.
Implements strict validation for user inputs to prevent injection attacks.
"""

import re
from typing import Optional


class ValidationError(Exception):
    """Custom validation error."""
    pass


def validate_username(username: str) -> str:
    """
    Validate username format.
    
    Args:
        username: Username to validate
        
    Returns:
        Cleaned username
        
    Raises:
        ValidationError: If username is invalid
    """
    if not username or len(username) < 3:
        raise ValidationError("Username must be at least 3 characters")
    if len(username) > 80:
        raise ValidationError("Username must not exceed 80 characters")
    
    # Allow alphanumeric, underscore, hyphen, dot
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", username):
        raise ValidationError("Username contains invalid characters")
    
    return username.strip()


def validate_password(password: str) -> str:
    """
    Validate password strength.
    
    Args:
        password: Password to validate
        
    Returns:
        Password if valid
        
    Raises:
        ValidationError: If password is too weak
    """
    if not password or len(password) < 6:
        raise ValidationError("Password must be at least 6 characters")
    if len(password) > 255:
        raise ValidationError("Password must not exceed 255 characters")
    
    return password


def validate_question(question: str) -> str:
    """
    Validate user question.
    
    Args:
        question: Question text
        
    Returns:
        Cleaned question
        
    Raises:
        ValidationError: If question is invalid
    """
    if not question or len(question.strip()) == 0:
        raise ValidationError("Question cannot be empty")
    if len(question) > 5000:
        raise ValidationError("Question is too long (max 5000 characters)")
    
    return question.strip()


def validate_filename(filename: str) -> str:
    """
    Validate filename for security.
    Prevents directory traversal and path injection attacks.
    
    Args:
        filename: Filename to validate
        
    Returns:
        Validated filename
        
    Raises:
        ValidationError: If filename is invalid
    """
    if not filename:
        raise ValidationError("Filename is required")
    
    # Remove path separators
    if "/" in filename or "\\" in filename:
        raise ValidationError("Filename contains invalid path characters")
    
    # Check for directory traversal
    if ".." in filename:
        raise ValidationError("Filename contains invalid characters")
    
    # Validate file extension
    allowed_extensions = {".pdf", ".docx", ".txt", ".md"}
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    
    if ext not in allowed_extensions:
        raise ValidationError(f"File type '{ext}' not allowed")
    
    return filename


def validate_model_name(model: Optional[str]) -> str:
    """
    Validate Ollama model name.
    
    Args:
        model: Model name (can be None for default)
        
    Returns:
        Model name or default
    """
    if not model:
        return "phi3:mini"
    
    if not re.match(r"^[a-zA-Z0-9_\-:]+$", model):
        raise ValidationError("Invalid model name")
    
    return model[:100]  # Limit length


def validate_role(role: str) -> str:
    """
    Validate user role.
    
    Args:
        role: Role name
        
    Returns:
        Validated role
        
    Raises:
        ValidationError: If role is invalid
    """
    if role not in ("admin", "user"):
        raise ValidationError(f"Invalid role '{role}'")
    
    return role


def validate_search_query(query: str) -> str:
    """
    Validate search query for chat history.
    
    Args:
        query: Search text
        
    Returns:
        Validated query (can be empty)
    """
    if not query:
        return ""
    
    if len(query) > 1000:
        return query[:1000]
    
    return query.strip()


def sanitize_html(text: str) -> str:
    """
    Escape HTML special characters to prevent XSS.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    replacements = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
    }
    
    result = str(text)
    for char, escaped in replacements.items():
        result = result.replace(char, escaped)
    
    return result
