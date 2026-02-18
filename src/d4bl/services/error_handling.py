"""
Error handling utilities for CrewAI agents and tools.
Provides retry logic, exponential backoff, and graceful error recovery.
"""
import time
import logging
from functools import wraps
from typing import Callable, TypeVar, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryStrategy(Enum):
    """Retry strategies for different error types."""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_DELAY = "fixed_delay"
    NO_RETRY = "no_retry"


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
    on_failure: Optional[Callable[[Exception], Any]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that retries a function with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff calculation
        retry_on: Tuple of exception types to retry on
        on_retry: Optional callback function called on each retry (exception, attempt_number)
        on_failure: Optional callback function called on final failure (exception)
    
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            delay = initial_delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retry_on as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        if on_retry:
                            on_retry(e, attempt + 1)
                        
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: {str(e)}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        
                        time.sleep(min(delay, max_delay))
                        delay *= exponential_base
                    else:
                        logger.error(
                            f"All {max_retries + 1} attempts failed for {func.__name__}: {str(e)}"
                        )
                        if on_failure:
                            return on_failure(e)
                        raise
            
            # This should never be reached, but type checker needs it
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected error in retry logic")
        
        return wrapper
    return decorator


def safe_execute(
    func: Callable[..., T],
    default_return: Optional[T] = None,
    error_message: Optional[str] = None,
    log_error: bool = True,
) -> Optional[T]:
    """
    Safely execute a function, catching all exceptions and returning a default value.
    
    Args:
        func: Function to execute
        default_return: Value to return on error (if None, exception is re-raised)
        error_message: Custom error message to log
        log_error: Whether to log the error
    
    Returns:
        Function result or default_return on error
    """
    try:
        return func()
    except Exception as e:
        if log_error:
            msg = error_message or f"Error executing {func.__name__}"
            logger.error(f"{msg}: {str(e)}", exc_info=True)
        
        if default_return is not None:
            return default_return
        raise


class ErrorRecoveryStrategy:
    """Manages error recovery strategies for different failure scenarios."""
    
    @staticmethod
    def fallback_to_firecrawl(error: Exception, context: dict[str, Any]) -> Optional[Any]:
        """Fallback to Firecrawl if Crawl4AI fails."""
        if "Crawl4AI" in str(error) or "crawl4ai" in str(error).lower():
            logger.info("Crawl4AI failed, attempting fallback to Firecrawl...")
            try:
                from crewai_tools import FirecrawlSearchTool
                firecrawl_api_key = context.get("firecrawl_api_key")
                if firecrawl_api_key:
                    tool = FirecrawlSearchTool(api_key=firecrawl_api_key)
                    query = context.get("query", "")
                    return tool._run(query=query)
            except Exception as fallback_error:
                logger.error(f"Firecrawl fallback also failed: {str(fallback_error)}")
        return None
    
    @staticmethod
    def return_partial_results(error: Exception, context: dict[str, Any]) -> dict[str, Any]:
        """Return partial results when full execution fails."""
        return {
            "error": str(error),
            "partial_results": context.get("partial_results", []),
            "status": "partial_failure"
        }
    
    @staticmethod
    def retry_with_simplified_query(error: Exception, context: dict[str, Any]) -> Optional[Any]:
        """Retry with a simplified/truncated query."""
        original_query = context.get("query", "")
        if len(original_query) > 100:
            simplified_query = original_query[:100] + "..."
            logger.info(f"Retrying with simplified query: {simplified_query}")
            context["query"] = simplified_query
            # This would need to be called from the retry decorator
        return None

