"""Document chunking utilities for RAG."""
from typing import List, Dict, Any, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
import tiktoken
import logging
import re

from temporal.config import config

logger = logging.getLogger(__name__)

# Module-level cache for tiktoken encodings (performance optimization)
_tiktoken_cache: Dict[str, tiktoken.Encoding] = {}


def get_encoding(model: str = "gpt-3.5-turbo") -> tiktoken.Encoding:
    """Get cached tiktoken encoding."""
    if model not in _tiktoken_cache:
        _tiktoken_cache[model] = tiktoken.encoding_for_model(model)
    return _tiktoken_cache[model]


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """Count tokens in text using cached tiktoken encoding."""
    try:
        encoding = get_encoding(model)
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"Token counting failed: {e}, using approximate count")
        return len(text) // 4  # Rough approximation


def classify_requirement_type(text: str) -> str:
    """Fast regex-based requirement type classification."""
    text_lower = text.lower()
    if re.search(r'\b(must|shall|required|mandatory)\b', text_lower):
        return "functional"
    elif re.search(r'\b(should|may|optional|recommended)\b', text_lower):
        return "non-functional"
    elif re.search(r'\b(constraint|limit|restriction|boundary|must not|cannot)\b', text_lower):
        return "constraint"
    elif re.search(r'\b(acceptance|criteria|test|verify|validate|success)\b', text_lower):
        return "acceptance_criteria"
    return "general"


def detect_constraints(text: str) -> bool:
    """Quick check for constraint indicators."""
    return bool(re.search(r'\b(constraint|limit|restriction|must not|cannot|boundary)\b', text.lower()))


def detect_success_criteria(text: str) -> bool:
    """Quick check for success criteria indicators."""
    return bool(re.search(r'\b(acceptance|criteria|success|pass|verify|validate)\b', text.lower()))


def extract_priority(text: str) -> Optional[str]:
    """Extract priority indicators from text."""
    text_lower = text.lower()
    if re.search(r'\b(critical|urgent|p0|priority 0)\b', text_lower):
        return "critical"
    elif re.search(r'\b(high|important|p1|priority 1)\b', text_lower):
        return "high"
    elif re.search(r'\b(medium|normal|p2|priority 2)\b', text_lower):
        return "medium"
    elif re.search(r'\b(low|nice to have|p3|priority 3)\b', text_lower):
        return "low"
    return None


def chunk_document(
    text: str,
    document_id: int,
    project_id: int,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    separators: Optional[List[str]] = None,
    document_metadata: Optional[Dict[str, Any]] = None,
    project_metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Chunk a document into semantic pieces with enriched metadata.
    
    Args:
        text: Document text content
        document_id: Document ID for metadata
        project_id: Project ID for metadata
        chunk_size: Maximum chunk size in characters
        chunk_overlap: Overlap between chunks in characters
        separators: List of separators to use for splitting
        document_metadata: Optional dict with document_name, document_type, version_number
        project_metadata: Optional dict with project_name, project_type
        
    Returns:
        List of chunk dictionaries with text and enriched metadata
    """
    if not text or not text.strip():
        logger.warning(f"Empty text provided for document {document_id}")
        return []
    
    # Use config defaults if not provided
    chunk_size = chunk_size or config.chunking.chunk_size
    chunk_overlap = chunk_overlap or config.chunking.chunk_overlap
    separators = separators or config.chunking.chunk_separators
    
    # Optimize chunking for large documents
    # For very large documents (>100KB), use simple character-based splitting for speed
    use_fast_path = len(text) > 100000
    
    if use_fast_path:
        # Fast path: simple character-based chunking
        logger.debug(f"Using fast chunking path for large document ({len(text)} chars)")
        chunks = []
        for i in range(0, len(text), chunk_size - chunk_overlap):
            chunk = text[i:i + chunk_size]
            if chunk.strip():  # Only add non-empty chunks
                chunks.append(chunk)
    else:
        # Standard path: use RecursiveCharacterTextSplitter for better semantic boundaries
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators,
            length_function=len,
        )
        chunks = text_splitter.split_text(text)
    
    # Build chunk metadata with optimized position tracking
    chunk_objects = []
    current_pos = 0
    
    # Use fast token approximation for large documents (skip actual counting)
    use_token_approximation = len(text) > 50000
    
    for index, chunk_text in enumerate(chunks):
        # Optimized position tracking: calculate directly instead of using text.find()
        start_pos = current_pos
        end_pos = current_pos + len(chunk_text)
        
        # Fast token counting: use approximation for large docs, actual count for small ones
        if use_token_approximation:
            token_count = len(chunk_text) // 4  # Fast approximation
        else:
            token_count = count_tokens(chunk_text)
        
        # Semantic classification (fast regex-based)
        requirement_type = classify_requirement_type(chunk_text)
        has_constraints = detect_constraints(chunk_text)
        has_success_criteria = detect_success_criteria(chunk_text)
        priority = extract_priority(chunk_text)
        
        # Build enriched metadata
        metadata = {
            # Existing metadata
            "start_pos": start_pos,
            "end_pos": end_pos,
            "chunk_size": len(chunk_text),
            "token_count": token_count,
            "chunk_index": index,
            
            # NEW: Document context
            "document_name": document_metadata.get("document_name") if document_metadata else None,
            "document_type": document_metadata.get("document_type") if document_metadata else None,
            "document_version": document_metadata.get("version_number") if document_metadata else None,
            
            # NEW: Project context
            "project_name": project_metadata.get("project_name") if project_metadata else None,
            "project_type": project_metadata.get("project_type") if project_metadata else None,
            
            # NEW: Semantic classification
            "requirement_type": requirement_type,
            "has_constraints": has_constraints,
            "has_success_criteria": has_success_criteria,
            "priority_indicators": priority,
        }
        
        chunk_obj = {
            "document_id": document_id,
            "project_id": project_id,
            "chunk_index": index,
            "chunk_text": chunk_text,
            "chunk_metadata": metadata,
        }
        
        chunk_objects.append(chunk_obj)
        
        # Update position accounting for overlap
        current_pos = end_pos - chunk_overlap if index < len(chunks) - 1 else end_pos
    
    logger.info(f"Chunked document {document_id} into {len(chunk_objects)} chunks (fast_path={use_fast_path})")
    return chunk_objects


def extract_document_content(document: Dict[str, Any]) -> str:
    """
    Extract text content from document dictionary.
    
    Prioritizes:
    1. raw_text_content
    2. file_content (converted from bytes)
    3. structured_json (if contains text)
    """
    # Try raw_text_content first
    if document.get("raw_text_content"):
        return document["raw_text_content"]
    
    # Try file_content (bytes)
    file_content = document.get("file_content")
    if file_content:
        if isinstance(file_content, bytes):
            try:
                return file_content.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning(f"Failed to decode file_content for document {document.get('document_id')}")
        elif isinstance(file_content, str):
            return file_content
    
    # Try structured_json
    structured_json = document.get("structured_json")
    if structured_json:
        if isinstance(structured_json, dict):
            # Try common text fields
            for field in ["content", "text", "body", "description"]:
                if field in structured_json:
                    text = structured_json[field]
                    if isinstance(text, str):
                        return text
    
    logger.warning(f"No extractable text content found for document {document.get('document_id')}")
    return ""

