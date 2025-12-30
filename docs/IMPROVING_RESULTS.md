# Options to Improve Research Results Quality

## Implementation Status

**Last Updated**: Recent improvements implemented

### ✅ Recently Implemented

1. **Content Filtering** (`crawl_tools.py`):
   - Added `_is_valid_content()` to validate crawl results
   - Added `_filter_valid_results()` to filter out empty/invalid results
   - Results with no extracted content are now filtered before being passed to agents
   - Logs warnings when results are filtered

2. **Relevance Validation** (`research_runner.py`):
   - Added `validate_research_relevance()` function
   - Checks keyword overlap between query and research output
   - Warns when output may be off-topic
   - Validates research task outputs in real-time

3. **✅ Enhanced PDF Extraction** (`crawl_tools.py`):
   - **Client-side PDF extraction fallback**: Uses `pypdf` library to extract PDF content when Crawl4AI API fails
   - **Improved API parameters**: Sends proper PDF extraction parameters to Crawl4AI API
   - **Separate PDF handling**: Processes PDFs separately with optimized extraction strategies
   - **Automatic fallback**: If API extraction fails, automatically tries client-side extraction
   - **Metadata extraction**: Extracts PDF metadata (title, author, etc.) when available
   - **Multi-page support**: Extracts text from all PDF pages
   - Added `pypdf>=3.0.0` to requirements.txt

### 📋 Next Steps

See "Recommended Implementation Order" section below for prioritized next steps.

---

## Current Issues Identified

1. **PDF Extraction Failing**: PDFs are crawled but `extracted_content` is null, resulting in empty content
2. **Evaluations Run Too Late**: Evaluations only execute after the entire report is generated, providing no feedback loop
3. **Off-Topic Results**: Agents sometimes produce answers unrelated to the query (e.g., DCU resources instead of algorithmic bias)
4. **No Real-Time Quality Checks**: No mechanism to catch quality issues during the research process

## Improvement Options

### Option 1: Fix PDF Extraction in Crawl4AI (High Priority)

**Problem**: PDFs are being crawled but content extraction fails (`extracted_content: null`, `cleaned_html: "<html></html>"`)

**Solutions**:

1. **Configure Crawl4AI for PDF extraction**:
   - Update the Crawl4AI service to use PDF extraction libraries (PyPDF2, pdfplumber, or pypdf)
   - Ensure the `/crawl` endpoint accepts PDF-specific extraction parameters
   - Add `extraction_strategy: "pdf"` or similar parameter to crawl requests

2. **Add PDF extraction fallback in `crawl_tools.py`**:
   ```python
   # In _crawl_urls_with_retry, check for PDFs and handle separately
   if any(url.endswith('.pdf') for url in urls):
       # Use alternative PDF extraction method
       # Or download and extract PDFs client-side
   ```

3. **Use Firecrawl for PDFs**: Firecrawl has better PDF extraction - route PDF URLs to Firecrawl instead of Crawl4AI

**Implementation**: Modify `src/d4bl/agents/tools/crawl_tools.py` to detect PDFs and handle them appropriately.

---

### Option 2: Run Evaluations After Each Task (Medium Priority)

**Problem**: Evaluations only run after the full report is generated, missing opportunities for early feedback

**Solutions**:

1. **Task-Level Evaluations**: Run quick quality checks after each agent task completes
   - After `research_task`: Check relevance and source quality
   - After `analysis_task`: Check accuracy and completeness
   - After `writing_task`: Check clarity and structure

2. **Early Termination on Low Quality**: If early evaluations show poor quality, stop the pipeline and request more research

3. **Incremental Evaluation**: Store evaluation results after each task and aggregate at the end

**Implementation**: 
- Add evaluation hooks in `research_runner.py` after each task output is processed
- Create lightweight evaluation functions that run quickly
- Store intermediate evaluation results in the job status

**Code Location**: `src/d4bl/services/research_runner.py` lines 321-378 (task output processing)

---

### Option 3: Add Real-Time Quality Checks During Research (High Priority)

**Problem**: No feedback mechanism during the research process to catch issues early

**Solutions**:

1. **Source Quality Validation**: After crawling, immediately check:
   - Is extracted content non-empty?
   - Does content match the query topic?
   - Are sources relevant?

2. **Content Relevance Check**: Before passing to next agent, verify:
   - Research output addresses the query
   - No obvious off-topic content
   - Sufficient information gathered

3. **Agent Output Validation**: After each agent completes, run a quick relevance check:
   ```python
   def quick_relevance_check(query: str, output: str) -> float:
       # Use a lightweight LLM call to score relevance 0-1
       # If score < 0.5, flag for review or retry
   ```

**Implementation**: 
- Add validation functions in `research_runner.py`
- Integrate with CrewAI task callbacks or custom validation layer
- Log warnings when quality thresholds aren't met

---

### Option 4: Improve Agent Prompts and Instructions (Medium Priority)

**Problem**: Agents sometimes produce off-topic results, suggesting prompts may need refinement

**Solutions**:

1. **Strengthen Query Focus in Prompts**: 
   - Add explicit instructions to stay on-topic
   - Include the original query in every agent's context
   - Add examples of good vs. bad outputs

2. **Add Validation Instructions**: 
   - Instruct agents to self-check their output against the query
   - Require agents to explicitly state if they couldn't find relevant information

3. **Improve Task Dependencies**: 
   - Ensure each task explicitly references the query
   - Add query validation steps between tasks

**Implementation**: 
- Update `src/d4bl/agents/config/agents.yaml` and `tasks.yaml`
- Add query validation to task descriptions

---

### Option 5: Add Content Filtering and Validation (High Priority)

**Problem**: Empty or irrelevant content is being passed through the pipeline

**Solutions**:

1. **Filter Empty Crawl Results**: 
   ```python
   # In crawl_tools.py, after receiving crawl results
   filtered_results = [
       r for r in results 
       if r.get('extracted_content') or r.get('cleaned_html', '').strip() != '<html></html>'
   ]
   ```

2. **Content Length Validation**: 
   - Reject crawl results with content < 100 characters
   - Flag results that are mostly HTML structure without text

3. **Relevance Pre-Filtering**: 
   - Before passing to agents, filter out clearly irrelevant sources
   - Use keyword matching or lightweight LLM check

**Implementation**: 
- Add filtering in `Crawl4AISearchTool._crawl_urls_with_retry()`
- Add validation layer in `research_runner.py` before processing results

---

### Option 6: Implement Retry Logic with Quality Gates (Medium Priority)

**Problem**: When results are poor, there's no automatic retry mechanism

**Solutions**:

1. **Quality-Gated Retries**: 
   - After research task, if quality < threshold, automatically retry with different search terms
   - After analysis task, if relevance < threshold, request more research

2. **Adaptive Search**: 
   - If initial search returns poor results, automatically refine search query
   - Use evaluation feedback to improve subsequent searches

3. **Multi-Pass Research**: 
   - Run research task multiple times with different angles
   - Aggregate and deduplicate results

**Implementation**: 
- Add retry logic in `research_runner.py` after task completion
- Integrate with evaluation results to trigger retries

---

### Option 7: Improve Error Handling for Failed Crawls (Low Priority)

**Problem**: When PDFs or pages fail to extract, the error isn't handled gracefully

**Solutions**:

1. **Better Error Messages**: 
   - Log specific reasons for extraction failures
   - Provide actionable error messages

2. **Fallback Strategies**: 
   - If PDF extraction fails, try alternative methods
   - If Crawl4AI fails, automatically try Firecrawl

3. **Partial Success Handling**: 
   - Continue with successfully extracted sources even if some fail
   - Log failures but don't stop the entire pipeline

**Implementation**: 
- Enhance error handling in `crawl_tools.py`
- Improve logging and error reporting

---

## Recommended Implementation Order

1. **Immediate (Fix Critical Issues)**:
   - Option 5: Add Content Filtering (prevents empty content from propagating)
   - Option 1: Fix PDF Extraction (ensures all sources are usable)

2. **Short Term (Improve Quality)**:
   - Option 3: Add Real-Time Quality Checks (catch issues early)
   - Option 4: Improve Agent Prompts (reduce off-topic results)

3. **Medium Term (Enhance Feedback Loop)**:
   - Option 2: Run Evaluations After Each Task (provide incremental feedback)
   - Option 6: Implement Retry Logic (auto-correct poor results)

4. **Long Term (Polish)**:
   - Option 7: Improve Error Handling (better user experience)

---

## Quick Wins

These can be implemented immediately with minimal code changes:

1. **✅ Filter empty crawl results** in `crawl_tools.py`:
   - **IMPLEMENTED**: Added `_is_valid_content()` and `_filter_valid_results()` methods
   - Filters out results with no extracted content, empty HTML, or insufficient text
   - Logs warnings when results are filtered
   - Tracks filtered vs valid results in response

2. **✅ Add content validation** in research runner:
   - **IMPLEMENTED**: Added `validate_research_relevance()` function
   - Checks keyword overlap between query and output
   - Warns when research output may be off-topic
   - Validates research task outputs in real-time

3. **✅ Improve PDF handling**:
   - **IMPLEMENTED**: Added PDF detection and extraction parameters
   - Automatically requests PDF extraction when PDFs are detected
   - Logs warnings when PDFs have no extracted content

4. **TODO**: Add query validation in agent prompts - ensure query is included in every task context

5. **TODO**: Log crawl failures more clearly to identify patterns

---

## Metrics to Track

To measure improvement, track:
- **Source extraction success rate**: % of URLs that return usable content
- **Relevance score**: How well results match the query (from evaluations)
- **Early quality detection**: % of issues caught before final report
- **Retry rate**: How often we need to retry due to quality issues
- **PDF extraction success rate**: % of PDFs successfully extracted

