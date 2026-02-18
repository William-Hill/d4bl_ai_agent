"""
PDF extraction utilities for client-side PDF processing.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Try to import PDF extraction library for fallback
try:
    from pypdf import PdfReader
    PDF_EXTRACTION_AVAILABLE = True
except ImportError:
    try:
        from PyPDF2 import PdfReader
        PDF_EXTRACTION_AVAILABLE = True
    except ImportError:
        PDF_EXTRACTION_AVAILABLE = False
        logger.warning(
            "PDF extraction libraries (pypdf or PyPDF2) not available. "
            "Install pypdf for client-side PDF extraction fallback."
        )


def is_valid_content(result: dict) -> bool:
    """Check if a crawl result has valid, extractable content."""
    # Check for extracted content
    extracted = result.get("extracted_content", "")
    if extracted and len(str(extracted).strip()) > 50:
        return True
    
    # Check for cleaned HTML (must have actual content, not just structure)
    cleaned_html = result.get("cleaned_html", "")
    if cleaned_html:
        # Remove HTML tags and check text length
        text_content = re.sub(r'<[^>]+>', '', str(cleaned_html))
        if len(text_content.strip()) > 50:
            return True
    
    # Check for raw HTML (must have substantial text content)
    html = result.get("html", "")
    if html:
        text_content = re.sub(r'<[^>]+>', '', str(html))
        # Filter out common empty HTML patterns
        empty_patterns = [
            r'^<html></html>$',
            r'^<html><head></head><body></body></html>$',
            r'^<html><body[^>]*></body></html>$',
        ]
        for pattern in empty_patterns:
            if re.match(pattern, str(html).strip(), re.IGNORECASE):
                return False
        if len(text_content.strip()) > 50:
            return True
    
    # PDF files might have null extracted_content but should be flagged
    url = result.get("url", "")
    if url and url.lower().endswith('.pdf'):
        logger.warning(
            "PDF file %s has no extracted content. PDF extraction may have failed.",
            url
        )
    
    return False


def extract_pdf_client_side(url: str, timeout: int = 60) -> Optional[dict]:
    """
    Fallback: Extract PDF content client-side if Crawl4AI fails.
    Downloads the PDF and extracts text using pypdf.
    """
    if not PDF_EXTRACTION_AVAILABLE:
        logger.warning("PDF extraction library not available, skipping client-side extraction")
        return None
    
    try:
        logger.info("Attempting client-side PDF extraction for: %s", url)
        
        # Download PDF with proper headers to handle various servers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/pdf,application/octet-stream,*/*',
        }
        
        # Download PDF with redirect handling
        response = requests.get(
            url, 
            timeout=timeout * 2,  # PDFs may take longer
            stream=True,
            headers=headers,
            allow_redirects=True
        )
        response.raise_for_status()
        
        # Check content type
        content_type = response.headers.get('Content-Type', '').lower()
        if 'pdf' not in content_type and not url.lower().endswith('.pdf'):
            logger.warning("URL does not appear to be a PDF (Content-Type: %s)", content_type)
            # Continue anyway, might still be a PDF
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(response.content)
            tmp_path = tmp_file.name
        
        try:
            # Extract text from PDF
            reader = PdfReader(tmp_path)
            text_content = []
            metadata = {}
            
            # Extract metadata if available
            if reader.metadata:
                metadata = {
                    "title": reader.metadata.get("/Title", ""),
                    "author": reader.metadata.get("/Author", ""),
                    "subject": reader.metadata.get("/Subject", ""),
                    "creator": reader.metadata.get("/Creator", ""),
                }
            
            # Extract text from all pages
            for page_num, page in enumerate(reader.pages, start=1):
                try:
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        text_content.append(f"--- Page {page_num} ---\n{page_text}")
                except Exception as page_error:
                    logger.warning("Error extracting text from page %s: %s", page_num, page_error)
                    continue
            
            extracted_text = "\n\n".join(text_content)
            
            if not extracted_text or len(extracted_text.strip()) < 50:
                logger.warning("PDF extraction produced minimal content (%s chars)", len(extracted_text))
                return None
            
            logger.info(
                "Successfully extracted %s characters from PDF (%s pages)",
                len(extracted_text),
                len(reader.pages)
            )
            
            # Return in Crawl4AI-compatible format
            return {
                "url": url,
                "extracted_content": extracted_text,
                "cleaned_html": f"<html><body><pre>{extracted_text[:1000]}...</pre></body></html>",
                "html": f"<html><body><pre>{extracted_text[:1000]}...</pre></body></html>",
                "metadata": metadata,
                "success": True,
                "extraction_method": "client_side_pypdf",
                "page_count": len(reader.pages),
            }
        
        finally:
            # Clean up temporary file
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_error:
                logger.warning("Error cleaning up temp PDF file: %s", cleanup_error)
    
    except requests.exceptions.RequestException as e:
        logger.error("Failed to download PDF for client-side extraction: %s", e)
        logger.debug("PDF URL: %s, Error type: %s", url, type(e).__name__)
        return None
    except Exception as e:
        logger.error("Error during client-side PDF extraction: %s", e, exc_info=True)
        logger.debug("PDF URL: %s, Error details: %s", url, str(e))
        return None

