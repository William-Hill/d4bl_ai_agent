"""
Langfuse evaluation functions for research quality assessment.
Evaluates research outputs for accuracy, completeness, bias, and relevance.
"""
import os
import json
import time
from typing import Optional, Dict, Any, List
from langfuse import Langfuse  # type: ignore
import logging

logger = logging.getLogger(__name__)

# Configure logging format for evaluations
eval_logger = logging.getLogger(f"{__name__}.evaluations")
eval_logger.setLevel(logging.INFO)

_langfuse_client: Optional[Langfuse] = None


def _call_llm_text(llm, prompt: str, max_retries: int = 2, retry_delay: float = 2.0) -> str:
    """
    Call a CrewAI LLM (or compatible) and return text content.
    Uses the available callable interface: .call(prompt) or callable(llm)(prompt).
    """
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            if hasattr(llm, "call"):
                result = llm.call(prompt)
            elif callable(llm):
                result = llm(prompt)
            else:
                raise ValueError("LLM object is not callable and has no .call method")

            # Extract text content
            if hasattr(result, "content"):
                text = str(result.content)
            else:
                text = str(result)

            if not text or not text.strip():
                raise ValueError("LLM returned empty response")

            return text
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = retry_delay * (attempt + 1)
                logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}"
                )
                time.sleep(wait_time)
            else:
                logger.error(f"LLM call failed after {max_retries} attempts: {e}", exc_info=True)
                raise ValueError(f"LLM invocation failed: {str(e)}") from e

    raise ValueError(f"LLM invocation failed: {str(last_error)}")  # safety net


def get_langfuse_eval_client() -> Optional[Langfuse]:
    """Get or initialize Langfuse client for evaluations."""
    global _langfuse_client
    
    if _langfuse_client is not None:
        return _langfuse_client
    
    try:
        langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        langfuse_host = os.getenv("LANGFUSE_HOST", "http://localhost:3002")
        
        logger.debug(f"Initializing Langfuse client - Host: {langfuse_host}")
        
        if not langfuse_public_key or not langfuse_secret_key:
            logger.warning("Langfuse credentials not found. Evaluations will be disabled.")
            logger.debug(f"LANGFUSE_PUBLIC_KEY present: {bool(langfuse_public_key)}")
            logger.debug(f"LANGFUSE_SECRET_KEY present: {bool(langfuse_secret_key)}")
            return None
        
        # Adjust host for Docker
        if os.path.exists("/.dockerenv") and "localhost" in langfuse_host:
            original_host = langfuse_host
            langfuse_host = langfuse_host.replace("localhost", "langfuse-web")
            if ":3002" in langfuse_host:
                langfuse_host = langfuse_host.replace(":3002", ":3000")
            logger.debug(f"Adjusted host for Docker: {original_host} -> {langfuse_host}")
        
        _langfuse_client = Langfuse(
            public_key=langfuse_public_key,
            secret_key=langfuse_secret_key,
            host=langfuse_host
        )
        logger.info("✅ Langfuse evaluation client initialized successfully")
        logger.debug(f"Langfuse client configured with host: {langfuse_host}")
        return _langfuse_client
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse client: {e}", exc_info=True)
        logger.debug(f"Exception type: {type(e).__name__}")
        return None


def evaluate_research_quality(
    query: str,
    research_output: str,
    sources: List[str],
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluate research output quality using Langfuse.
    
    Args:
        query: Original research query
        research_output: Generated research output/response
        sources: List of source URLs used
        trace_id: Optional trace ID to link evaluation to original trace
    
    Returns:
        Dictionary with evaluation scores and feedback
    """
    start_time = time.time()
    eval_logger.info("Starting research quality evaluation")
    eval_logger.debug(f"Query length: {len(query)}, Output length: {len(research_output)}, Sources: {len(sources)}")
    eval_logger.debug(f"Trace ID: {trace_id[:16] + '...' if trace_id and len(trace_id) > 16 else trace_id}")
    
    langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping research quality evaluation")
        return {"error": "Langfuse not configured", "status": "skipped"}
    
    try:
        # Validate inputs
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if not research_output or not research_output.strip():
            raise ValueError("Research output cannot be empty")
        
        eval_logger.debug("Input validation passed")
        # Create evaluation prompt
        eval_prompt = f"""Evaluate the following research output for quality:

Original Query: {query}

Research Output:
{research_output[:2000]}...

Sources Used: {len(sources)} sources
{chr(10).join(f"- {s}" for s in sources[:5])}

Evaluate on the following criteria (1-5 scale):
1. Relevance: How well does the output address the query?
2. Completeness: How comprehensive is the information provided?
3. Accuracy: Are claims supported by sources?
4. Bias: Is the output balanced and free from harmful bias?
5. Clarity: Is the output well-structured and clear?

Provide scores and brief explanations for each criterion. Format as JSON with keys: relevance, completeness, accuracy, bias, clarity, overall, feedback."""

        # Use CrewAI LLM helper (callable or .call) to generate evaluation
        eval_logger.debug("Initializing LLM for evaluation via CrewAI helper")
        try:
            from d4bl.llm import get_ollama_llm
            llm = get_ollama_llm()
            eval_logger.debug("LLM initialized successfully")
        except Exception as llm_error:
            logger.error(f"Failed to initialize LLM for evaluation: {llm_error}", exc_info=True)
            raise ValueError(f"LLM initialization failed: {str(llm_error)}") from llm_error

        llm_start = time.time()
        evaluation = _call_llm_text(llm, eval_prompt, max_retries=2, retry_delay=2.0)
        eval_logger.debug(f"LLM call successful in {time.time() - llm_start:.2f}s")

        # Parse evaluation response
        eval_text = str(evaluation)
        eval_logger.debug(f"Evaluation response length: {len(eval_text)}")
        
        # Try to extract JSON from response
        import re
        json_match = re.search(r'\{[^{}]*\}', eval_text, re.DOTALL)
        if json_match:
            try:
                scores = json.loads(json_match.group())
                eval_logger.debug("Successfully parsed JSON from evaluation response")
            except json.JSONDecodeError as json_error:
                logger.warning(f"Failed to parse JSON from evaluation response: {json_error}")
                logger.debug(f"JSON match text: {json_match.group()[:200]}")
                scores = {}
        else:
            logger.warning("No JSON found in evaluation response")
            logger.debug(f"Evaluation response preview: {eval_text[:200]}")
            scores = {}
        
        # Default scores if parsing failed
        scores.setdefault("relevance", 3.0)
        scores.setdefault("completeness", 3.0)
        scores.setdefault("accuracy", 3.0)
        scores.setdefault("bias", 3.0)
        scores.setdefault("clarity", 3.0)
        scores.setdefault("overall", sum([scores.get("relevance", 3.0), scores.get("completeness", 3.0), 
                                         scores.get("accuracy", 3.0), scores.get("bias", 3.0), 
                                         scores.get("clarity", 3.0)]) / 5.0)
        scores.setdefault("feedback", eval_text[:500])
        
        eval_logger.info(f"Evaluation scores - Overall: {scores['overall']:.2f}, "
                        f"Relevance: {scores['relevance']:.2f}, Completeness: {scores['completeness']:.2f}, "
                        f"Accuracy: {scores['accuracy']:.2f}, Bias: {scores['bias']:.2f}, "
                        f"Clarity: {scores['clarity']:.2f}")
        
        # Log evaluation score to Langfuse using score_current_trace (correct API)
        if trace_id and langfuse:
            try:
                # Use score_current_trace to attach score to the active trace
                langfuse.score_current_trace(
                    name="research_quality",
                    value=scores["overall"],
                    data_type="NUMERIC",
                    comment=scores.get("feedback", "")[:500]
                )
                langfuse.flush()  # Ensure score is sent immediately
                eval_logger.debug(f"Score logged to Langfuse for trace_id: {trace_id[:16]}...")
            except Exception as score_error:
                logger.error(f"Failed to log score to Langfuse: {score_error}", exc_info=True)
                # Don't fail the evaluation if score logging fails
        
        elapsed_time = time.time() - start_time
        eval_logger.info(f"Research quality evaluation completed in {elapsed_time:.2f}s")
        
        return {
            "scores": scores,
            "trace_id": trace_id,
            "status": "success",
            "elapsed_time": elapsed_time
        }
        
    except ValueError as ve:
        logger.error(f"Validation error in research quality evaluation: {ve}", exc_info=True)
        return {"error": str(ve), "status": "failed", "error_type": "validation"}
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Error in research quality evaluation (took {elapsed_time:.2f}s): {e}", exc_info=True)
        return {"error": str(e), "status": "failed", "error_type": type(e).__name__, "elapsed_time": elapsed_time}


def evaluate_source_relevance(
    query: str,
    sources: List[str],
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluate how relevant the sources are to the query.
    
    Args:
        query: Original research query
        sources: List of source URLs
        trace_id: Optional trace ID
    
    Returns:
        Dictionary with relevance scores per source
    """
    start_time = time.time()
    eval_logger.info(f"Starting source relevance evaluation for {len(sources)} sources")
    
    langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping source relevance evaluation")
        return {"error": "Langfuse not configured", "status": "skipped"}
    
    try:
        # Validate inputs
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if not sources:
            logger.warning("No sources provided for relevance evaluation")
            return {
                "scores": {},
                "average": 0.0,
                "status": "skipped",
                "reason": "no_sources"
            }
        # Simple relevance check - can be enhanced with LLM
        relevance_scores = {}
        for idx, source in enumerate(sources):
            try:
                # Basic heuristic: check if query keywords appear in URL
                query_keywords = set(query.lower().split())
                url_lower = source.lower()
                matches = sum(1 for keyword in query_keywords if keyword in url_lower)
                relevance = min(5.0, (matches / len(query_keywords)) * 5) if query_keywords else 3.0
                relevance_scores[source] = relevance
                eval_logger.debug(f"Source {idx + 1}/{len(sources)}: relevance={relevance:.2f} ({matches}/{len(query_keywords)} matches)")
            except Exception as source_error:
                logger.warning(f"Error evaluating source {idx + 1} ({source[:50]}...): {source_error}")
                relevance_scores[source] = 3.0  # Default score on error
        
        avg_relevance = sum(relevance_scores.values()) / len(relevance_scores) if relevance_scores else 0.0
        eval_logger.info(f"Source relevance evaluation - Average: {avg_relevance:.2f}, "
                        f"Sources evaluated: {len(relevance_scores)}")
        
        # Log score to Langfuse (attach to current trace)
        if trace_id and langfuse:
            try:
                langfuse.score_current_trace(
                    name="source_relevance",
                    value=avg_relevance,
                    data_type="NUMERIC",
                    comment=f"Average relevance of {len(sources)} sources"
                )
                langfuse.flush()
                eval_logger.debug("Source relevance score logged to Langfuse")
            except Exception as score_error:
                logger.error(f"Failed to log source relevance score to Langfuse: {score_error}", exc_info=True)
        
        elapsed_time = time.time() - start_time
        eval_logger.info(f"Source relevance evaluation completed in {elapsed_time:.2f}s")
        
        return {
            "scores": relevance_scores,
            "average": avg_relevance,
            "status": "success",
            "elapsed_time": elapsed_time
        }
        
    except ValueError as ve:
        logger.error(f"Validation error in source relevance evaluation: {ve}", exc_info=True)
        return {"error": str(ve), "status": "failed", "error_type": "validation"}
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Error in source relevance evaluation (took {elapsed_time:.2f}s): {e}", exc_info=True)
        return {"error": str(e), "status": "failed", "error_type": type(e).__name__, "elapsed_time": elapsed_time}


def evaluate_bias_detection(
    research_output: str,
    query: str,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Detect potential bias in research output.
    
    Args:
        research_output: Generated research output
        query: Original query
        trace_id: Optional trace ID
    
    Returns:
        Dictionary with bias detection results
    """
    start_time = time.time()
    eval_logger.info("Starting bias detection evaluation")
    
    langfuse = get_langfuse_eval_client()
    if not langfuse:
        logger.warning("Langfuse not available, skipping bias detection evaluation")
        return {"error": "Langfuse not configured", "status": "skipped"}
    
    try:
        # Validate inputs
        if not research_output or not research_output.strip():
            raise ValueError("Research output cannot be empty")
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        # Bias detection prompt
        bias_prompt = f"""Analyze the following research output for potential bias:

Query: {query}

Output:
{research_output[:2000]}...

Identify:
1. Any racial, gender, or other demographic bias
2. Confirmation bias or one-sided perspectives
3. Missing perspectives or underrepresented viewpoints
4. Language that may perpetuate stereotypes

Provide a bias score (1-5, where 1=highly biased, 5=balanced) and explanation. Format as JSON with keys: bias_score, feedback."""

        eval_logger.debug("Initializing LLM for bias detection via CrewAI helper")
        try:
            from d4bl.crew import get_ollama_llm
            llm = get_ollama_llm()
        except Exception as llm_error:
            logger.error(f"Failed to initialize LLM for bias detection: {llm_error}", exc_info=True)
            raise ValueError(f"LLM initialization failed: {str(llm_error)}") from llm_error
        
        # Invoke LLM with error handling
        llm_start = time.time()
        bias_feedback = _call_llm_text(llm, bias_prompt, max_retries=2, retry_delay=2.0)
        eval_logger.debug(f"LLM invocation successful in {time.time() - llm_start:.2f}s")
        
        # Parse bias score
        eval_logger.debug(f"Bias analysis response length: {len(bias_feedback)}")
        
        # Try to extract JSON from response
        import re
        json_match = re.search(r'\{[^{}]*\}', bias_feedback, re.DOTALL)
        if json_match:
            try:
                bias_data = json.loads(json_match.group())
                bias_score = float(bias_data.get("bias_score", 3.0))
                bias_feedback = bias_data.get("feedback", bias_feedback)
                eval_logger.debug("Successfully parsed JSON from bias analysis response")
            except (json.JSONDecodeError, ValueError, KeyError) as parse_error:
                logger.warning(f"Failed to parse JSON from bias analysis: {parse_error}")
                # Try to extract score from text
                score_match = re.search(r'bias[_\s]?score[:\s]+([0-9.]+)', bias_feedback, re.IGNORECASE)
                if score_match:
                    try:
                        bias_score = float(score_match.group(1))
                    except ValueError:
                        bias_score = 3.0
                else:
                    bias_score = 3.0
        else:
            logger.warning("No JSON found in bias analysis response, using default score")
            bias_score = 3.0
        
        # Ensure score is in valid range
        bias_score = max(1.0, min(5.0, float(bias_score)))
        
        eval_logger.info(f"Bias detection evaluation - Score: {bias_score:.2f}")
        
        # Log score to Langfuse (attach to current trace)
        if trace_id and langfuse:
            try:
                langfuse.score_current_trace(
                    name="bias_detection",
                    value=bias_score,
                    data_type="NUMERIC",
                    comment=bias_feedback[:500]
                )
                langfuse.flush()
                eval_logger.debug("Bias detection score logged to Langfuse")
            except Exception as score_error:
                logger.error(f"Failed to log bias detection score to Langfuse: {score_error}", exc_info=True)
        
        elapsed_time = time.time() - start_time
        eval_logger.info(f"Bias detection evaluation completed in {elapsed_time:.2f}s")
        
        return {
            "bias_score": bias_score,
            "feedback": bias_feedback[:500],
            "status": "success",
            "elapsed_time": elapsed_time
        }
        
    except ValueError as ve:
        logger.error(f"Validation error in bias detection: {ve}", exc_info=True)
        return {"error": str(ve), "status": "failed", "error_type": "validation"}
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Error in bias detection (took {elapsed_time:.2f}s): {e}", exc_info=True)
        return {"error": str(e), "status": "failed", "error_type": type(e).__name__, "elapsed_time": elapsed_time}


def run_comprehensive_evaluation(
    query: str,
    research_output: str,
    sources: List[str],
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run all evaluations and return comprehensive results.
    
    Args:
        query: Original research query
        research_output: Generated research output
        sources: List of source URLs
        trace_id: Optional trace ID
    
    Returns:
        Dictionary with all evaluation results
    """
    start_time = time.time()
    eval_logger.info("=" * 60)
    eval_logger.info("Starting comprehensive evaluation")
    eval_logger.info(f"Query: {query[:100]}...")
    eval_logger.info(f"Output length: {len(research_output)} chars")
    eval_logger.info(f"Sources: {len(sources)}")
    eval_logger.info(f"Trace ID: {trace_id[:16] + '...' if trace_id and len(trace_id) > 16 else trace_id}")
    eval_logger.info("=" * 60)
    
    results = {
        "query": query,
        "trace_id": trace_id,
        "evaluations": {},
        "start_time": start_time
    }
    
    # Run all evaluations with error handling
    eval_logger.info("Running research quality evaluation...")
    try:
        results["evaluations"]["quality"] = evaluate_research_quality(
            query=query,
            research_output=research_output,
            sources=sources,
            trace_id=trace_id
        )
        if results["evaluations"]["quality"].get("status") == "success":
            eval_logger.info("✅ Research quality evaluation completed successfully")
        else:
            eval_logger.warning(f"⚠️ Research quality evaluation status: {results['evaluations']['quality'].get('status')}")
    except Exception as e:
        logger.error(f"Failed to run research quality evaluation: {e}", exc_info=True)
        results["evaluations"]["quality"] = {"error": str(e), "status": "failed"}
    
    eval_logger.info("Running source relevance evaluation...")
    try:
        results["evaluations"]["source_relevance"] = evaluate_source_relevance(
            query=query,
            sources=sources,
            trace_id=trace_id
        )
        if results["evaluations"]["source_relevance"].get("status") == "success":
            eval_logger.info("✅ Source relevance evaluation completed successfully")
        else:
            eval_logger.warning(f"⚠️ Source relevance evaluation status: {results['evaluations']['source_relevance'].get('status')}")
    except Exception as e:
        logger.error(f"Failed to run source relevance evaluation: {e}", exc_info=True)
        results["evaluations"]["source_relevance"] = {"error": str(e), "status": "failed"}
    
    eval_logger.info("Running bias detection evaluation...")
    try:
        results["evaluations"]["bias"] = evaluate_bias_detection(
            research_output=research_output,
            query=query,
            trace_id=trace_id
        )
        if results["evaluations"]["bias"].get("status") == "success":
            eval_logger.info("✅ Bias detection evaluation completed successfully")
        else:
            eval_logger.warning(f"⚠️ Bias detection evaluation status: {results['evaluations']['bias'].get('status')}")
    except Exception as e:
        logger.error(f"Failed to run bias detection evaluation: {e}", exc_info=True)
        results["evaluations"]["bias"] = {"error": str(e), "status": "failed"}
    
    # Calculate overall score with error handling
    try:
        quality_score = results["evaluations"]["quality"].get("scores", {}).get("overall", 3.0)
        source_score = results["evaluations"]["source_relevance"].get("average", 3.0)
        bias_score = results["evaluations"]["bias"].get("bias_score", 3.0)
        
        # Use default scores if evaluations failed
        if results["evaluations"]["quality"].get("status") != "success":
            quality_score = 3.0
            eval_logger.warning("Using default quality score due to evaluation failure")
        if results["evaluations"]["source_relevance"].get("status") != "success":
            source_score = 3.0
            eval_logger.warning("Using default source relevance score due to evaluation failure")
        if results["evaluations"]["bias"].get("status") != "success":
            bias_score = 3.0
            eval_logger.warning("Using default bias score due to evaluation failure")
        
        overall_score = (quality_score + source_score + bias_score) / 3.0
        results["overall_score"] = overall_score
        
        eval_logger.info(f"Overall evaluation score: {overall_score:.2f}")
        eval_logger.info(f"  - Quality: {quality_score:.2f}")
        eval_logger.info(f"  - Source Relevance: {source_score:.2f}")
        eval_logger.info(f"  - Bias: {bias_score:.2f}")
        
    except Exception as score_error:
        logger.error(f"Failed to calculate overall score: {score_error}", exc_info=True)
        results["overall_score"] = 3.0
        results["score_calculation_error"] = str(score_error)
    
    elapsed_time = time.time() - start_time
    results["elapsed_time"] = elapsed_time
    results["status"] = "completed"
    
    # Determine final status
    successful_evals = sum(1 for eval_result in results["evaluations"].values() 
                          if eval_result.get("status") == "success")
    total_evals = len(results["evaluations"])
    
    if successful_evals == total_evals:
        results["status"] = "success"
        eval_logger.info("=" * 60)
        eval_logger.info(f"✅ Comprehensive evaluation completed successfully in {elapsed_time:.2f}s")
        eval_logger.info(f"   All {total_evals} evaluations passed")
        eval_logger.info("=" * 60)
    elif successful_evals > 0:
        results["status"] = "partial_success"
        eval_logger.warning("=" * 60)
        eval_logger.warning(f"⚠️ Comprehensive evaluation completed with partial success in {elapsed_time:.2f}s")
        eval_logger.warning(f"   {successful_evals}/{total_evals} evaluations passed")
        eval_logger.warning("=" * 60)
    else:
        results["status"] = "failed"
        eval_logger.error("=" * 60)
        eval_logger.error(f"❌ Comprehensive evaluation failed in {elapsed_time:.2f}s")
        eval_logger.error(f"   {successful_evals}/{total_evals} evaluations passed")
        eval_logger.error("=" * 60)
    
    return results

