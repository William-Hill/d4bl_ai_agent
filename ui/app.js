// D4BL AI Agent UI JavaScript

const API_BASE = window.location.origin;
let currentJobId = null;
let websocket = null;

// DOM Elements
const researchForm = document.getElementById('researchForm');
const submitBtn = document.getElementById('submitBtn');
const submitText = document.getElementById('submitText');
const submitSpinner = document.getElementById('submitSpinner');
const progressCard = document.getElementById('progressCard');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const resultsCard = document.getElementById('resultsCard');
const resultsContent = document.getElementById('resultsContent');
const errorCard = document.getElementById('errorCard');
const errorMessage = document.getElementById('errorMessage');

// Form submission
researchForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const query = document.getElementById('query').value.trim();
    const summaryFormat = document.getElementById('summaryFormat').value;
    
    if (!query) {
        showError('Please enter a research query');
        return;
    }
    
    // Reset UI
    hideError();
    hideResults();
    showProgress();
    
    // Disable form
    submitBtn.disabled = true;
    submitText.textContent = 'Starting...';
    submitSpinner.classList.remove('hidden');
    
    try {
        // Create research job
        const response = await fetch(`${API_BASE}/api/research`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query,
                summary_format: summaryFormat
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create research job');
        }
        
        const data = await response.json();
        currentJobId = data.job_id;
        
        // Connect WebSocket for real-time updates
        connectWebSocket(currentJobId);
        
        // Start polling as fallback
        pollJobStatus(currentJobId);
        
    } catch (error) {
        console.error('Error:', error);
        showError(error.message || 'An error occurred while starting the research');
        resetForm();
    }
});

// WebSocket connection
function connectWebSocket(jobId) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${jobId}`;
    
    websocket = new WebSocket(wsUrl);
    
    websocket.onopen = () => {
        console.log('WebSocket connected');
    };
    
    websocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };
    
    websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    websocket.onclose = () => {
        console.log('WebSocket disconnected');
        // Reconnect if job is still running
        if (currentJobId && document.getElementById('progressCard').classList.contains('hidden') === false) {
            setTimeout(() => connectWebSocket(currentJobId), 3000);
        }
    };
}

// Handle WebSocket messages
function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'status':
        case 'progress':
            updateProgress(data.progress || 'Processing...');
            break;
            
        case 'complete':
            updateProgress('Research completed!');
            displayResults(data.result);
            resetForm();
            if (websocket) {
                websocket.close();
            }
            break;
            
        case 'error':
            showError(data.error || 'An error occurred during research');
            resetForm();
            if (websocket) {
                websocket.close();
            }
            break;
    }
}

// Poll job status (fallback if WebSocket fails)
async function pollJobStatus(jobId) {
    const maxAttempts = 300; // 5 minutes max (1 second intervals)
    let attempts = 0;
    
    const poll = async () => {
        if (attempts >= maxAttempts) {
            showError('Research job timed out. Please try again.');
            resetForm();
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE}/api/jobs/${jobId}`);
            if (!response.ok) {
                throw new Error('Failed to fetch job status');
            }
            
            const job = await response.json();
            
            if (job.status === 'completed') {
                updateProgress('Research completed!');
                displayResults(job.result);
                resetForm();
                return;
            } else if (job.status === 'error') {
                showError(job.error || 'An error occurred during research');
                resetForm();
                return;
            } else if (job.status === 'running') {
                updateProgress(job.progress || 'Processing...');
                attempts++;
                setTimeout(poll, 1000);
            } else {
                attempts++;
                setTimeout(poll, 1000);
            }
        } catch (error) {
            console.error('Polling error:', error);
            attempts++;
            setTimeout(poll, 2000);
        }
    };
    
    poll();
}

// Update progress UI
function updateProgress(message) {
    progressText.textContent = message;
    // Animate progress bar (simplified - you could make this more sophisticated)
    const currentWidth = parseInt(progressFill.style.width) || 0;
    if (currentWidth < 90) {
        progressFill.style.width = Math.min(currentWidth + 10, 90) + '%';
    }
}

// Display results
function displayResults(result) {
    if (!result) {
        showError('No results returned');
        return;
    }
    
    hideProgress();
    showResults();
    
    let html = '';
    
    // Display report if available
    if (result.report) {
        html += `
            <div class="result-section">
                <h3>📄 Research Report</h3>
                <div class="markdown-content">${formatMarkdown(result.report)}</div>
            </div>
        `;
    }
    
    // Display task outputs
    if (result.tasks_output && result.tasks_output.length > 0) {
        result.tasks_output.forEach((task, index) => {
            html += `
                <div class="result-section">
                    <h3>${task.agent || `Task ${index + 1}`}</h3>
                    <pre>${escapeHtml(task.output || 'No output available')}</pre>
                </div>
            `;
        });
    }
    
    // Display raw output if no other results
    if (!result.report && (!result.tasks_output || result.tasks_output.length === 0)) {
        html += `
            <div class="result-section">
                <h3>Research Output</h3>
                <pre>${escapeHtml(result.raw_output || 'No output available')}</pre>
            </div>
        `;
    }
    
    resultsContent.innerHTML = html;
    
    // Scroll to results
    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Simple markdown formatter (for basic formatting)
function formatMarkdown(text) {
    if (!text) return '';
    
    // Escape HTML first
    let html = escapeHtml(text);
    
    // Headers
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
    
    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Italic
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    
    // Links
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
    
    // Line breaks
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');
    
    // Wrap in paragraph tags
    html = '<p>' + html + '</p>';
    
    // Lists (basic)
    html = html.replace(/^\- (.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    
    return html;
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// UI helpers
function showProgress() {
    progressCard.classList.remove('hidden');
    progressFill.style.width = '10%';
}

function hideProgress() {
    progressCard.classList.add('hidden');
}

function showResults() {
    resultsCard.classList.remove('hidden');
}

function hideResults() {
    resultsCard.classList.add('hidden');
    resultsContent.innerHTML = '';
}

function showError(message) {
    errorMessage.textContent = message;
    errorCard.classList.remove('hidden');
    errorCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function hideError() {
    errorCard.classList.add('hidden');
}

function clearError() {
    hideError();
}

function resetForm() {
    submitBtn.disabled = false;
    submitText.textContent = 'Start Research';
    submitSpinner.classList.add('hidden');
    progressFill.style.width = '0%';
}

