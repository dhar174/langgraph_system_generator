// DOM elements
const form = document.getElementById('generateForm');
const promptTextarea = document.getElementById('prompt');
const charCount = document.getElementById('charCount');
const generateBtn = document.getElementById('generateBtn');
const btnText = generateBtn.querySelector('.btn-text');
const spinner = generateBtn.querySelector('.spinner');
const resultCard = document.getElementById('resultCard');
const resultContent = document.getElementById('resultContent');
const errorCard = document.getElementById('errorCard');
const errorContent = document.getElementById('errorContent');
const healthStatus = document.getElementById('healthStatus');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const progressCard = document.getElementById('progressCard');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const progressPercentage = document.getElementById('progressPercentage');
const progressSteps = document.getElementById('progressSteps');

// Advanced options
const advancedToggle = document.getElementById('advancedToggle');
const advancedPanel = document.getElementById('advancedPanel');
const temperatureSlider = document.getElementById('temperature');
const tempValue = document.getElementById('tempValue');
const modelSelect = document.getElementById('model');
const customEndpointGroup = document.getElementById('customEndpointGroup');

// Theme toggle
const themeToggle = document.getElementById('themeToggle');
const themeIcon = themeToggle.querySelector('.theme-icon');

// Initialize theme from localStorage
const currentTheme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', currentTheme);
themeIcon.textContent = currentTheme === 'dark' ? '🌙' : '☀️';

// Theme toggle functionality
themeToggle.addEventListener('click', () => {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    themeIcon.textContent = newTheme === 'dark' ? '🌙' : '☀️';
});

// Advanced options toggle
advancedToggle.addEventListener('click', () => {
    const isExpanded = advancedToggle.getAttribute('aria-expanded') === 'true';
    
    if (isExpanded) {
        advancedPanel.style.display = 'none';
        advancedToggle.setAttribute('aria-expanded', 'false');
    } else {
        advancedPanel.style.display = 'block';
        advancedToggle.setAttribute('aria-expanded', 'true');
    }
});

// Temperature slider update
temperatureSlider.addEventListener('input', (e) => {
    tempValue.textContent = e.target.value;
});

// Model selection - show/hide custom endpoint field
modelSelect.addEventListener('change', (e) => {
    if (e.target.value === 'custom') {
        customEndpointGroup.style.display = 'block';
        document.getElementById('customEndpoint').required = true;
    } else {
        customEndpointGroup.style.display = 'none';
        document.getElementById('customEndpoint').required = false;
    }
});

// Helper to count Unicode characters (code points) for accurate counting
function getCharacterCount(text) {
    return Array.from(text || '').length;
}

// Update character count
promptTextarea.addEventListener('input', () => {
    const count = getCharacterCount(promptTextarea.value);
    charCount.textContent = count;
    
    // Visual feedback for character count
    if (count > 5000) {
        charCount.style.color = 'var(--error-color)';
        charCount.style.fontWeight = 'bold';
        promptTextarea.classList.add('invalid');
        promptTextarea.classList.remove('valid');
    } else if (count > 4500) {
        charCount.style.color = 'var(--warning-color)';
        charCount.style.fontWeight = 'bold';
        promptTextarea.classList.remove('invalid', 'valid');
    } else if (count >= 10) {
        charCount.style.color = 'var(--text-muted)';
        charCount.style.fontWeight = 'normal';
        promptTextarea.classList.add('valid');
        promptTextarea.classList.remove('invalid');
    } else {
        charCount.style.color = 'var(--text-muted)';
        charCount.style.fontWeight = 'normal';
        promptTextarea.classList.remove('invalid', 'valid');
    }
});

// Output directory validation
const outputDirInput = document.getElementById('outputDir');
outputDirInput.addEventListener('input', (e) => {
    const value = e.target.value.trim();
    
    // Basic path validation
    if (value.length === 0) {
        outputDirInput.classList.remove('valid', 'invalid');
        return;
    }
    
    // Check for invalid characters and common Windows path restrictions.
    // This is a conservative check to avoid obviously invalid or problematic paths;
    // the server should still perform authoritative validation.
    const invalidChars = /[<>"|?*\x00-\x1F]/;
    const windowsReservedNames = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$/i;
    const hasReservedName = value
        .split(/[\\/]/)
        .some((part) => windowsReservedNames.test(part));
    // Disallow colons that are not used as a drive letter separator (e.g. "C:\")
    const hasInvalidColonUsage = /:/.test(value) && !/^[a-zA-Z]:[\\/]/.test(value);

    if (invalidChars.test(value) || hasReservedName || hasInvalidColonUsage) {
        outputDirInput.classList.add('invalid');
        outputDirInput.classList.remove('valid');
    } else {
        outputDirInput.classList.add('valid');
        outputDirInput.classList.remove('invalid');
    }
});

// Check health status
async function checkHealth() {
    try {
        const response = await fetch('/health');
        if (response.ok) {
            statusDot.classList.add('healthy');
            statusDot.classList.remove('error');
            statusText.textContent = 'Server Online';
        } else {
            throw new Error('Health check failed');
        }
    } catch (error) {
        statusDot.classList.add('error');
        statusDot.classList.remove('healthy');
        statusText.textContent = 'Server Offline';
        console.error('Health check error:', error);
    }
}

// Show loading state
function setLoading(isLoading) {
    generateBtn.disabled = isLoading;
    if (isLoading) {
        btnText.textContent = 'Generating...';
        spinner.style.display = 'inline-block';
    } else {
        btnText.textContent = 'Generate System';
        spinner.style.display = 'none';
    }
}

// Hide all result cards
function hideResults() {
    resultCard.style.display = 'none';
    errorCard.style.display = 'none';
    progressCard.style.display = 'none';
}

// Progress steps configuration
const PROGRESS_STEPS = [
    { text: 'Validating input', percent: 10 },
    { text: 'Preparing generation context', percent: 25 },
    { text: 'Invoking LLM', percent: 50 },
    { text: 'Generating artifacts', percent: 75 },
    { text: 'Finalizing outputs', percent: 90 },
    { text: 'Complete', percent: 100 }
];

// Initialize progress steps once
function initProgressSteps() {
    progressSteps.innerHTML = '';
    PROGRESS_STEPS.forEach((s, index) => {
        const stepDiv = document.createElement('div');
        stepDiv.className = 'progress-step';
        stepDiv.dataset.stepPercent = s.percent;
        
        const icon = document.createElement('span');
        icon.className = 'step-icon';
        icon.setAttribute('aria-label', 'Step status');
        icon.textContent = '⏳';
        
        const text = document.createElement('span');
        text.className = 'step-text';
        text.textContent = s.text;
        
        stepDiv.appendChild(icon);
        stepDiv.appendChild(text);
        progressSteps.appendChild(stepDiv);
    });
}

// Show progress with steps (now just updates existing elements)
function showProgress(step, percentage, message) {
    hideResults();
    progressCard.style.display = 'block';
    progressFill.style.width = percentage + '%';
    progressPercentage.textContent = percentage + '%';
    progressText.textContent = message;
    
    // Initialize steps if not already done
    if (progressSteps.children.length === 0) {
        initProgressSteps();
    }
    
    // Update step states without recreating DOM
    Array.from(progressSteps.children).forEach((stepDiv) => {
        const stepPercent = parseInt(stepDiv.dataset.stepPercent);
        const icon = stepDiv.querySelector('.step-icon');
        
        // Remove previous classes
        stepDiv.classList.remove('complete', 'active');
        
        if (percentage >= stepPercent) {
            stepDiv.classList.add('complete');
            icon.textContent = '✅';
        } else if (Math.abs(percentage - stepPercent) < 15) {
            stepDiv.classList.add('active');
            icon.textContent = '⏳';
        } else {
            icon.textContent = '⏳';
        }
    });
}

// Show success result
function showResult(data) {
    hideResults();
    
    const manifest = data.manifest || {};
    const mode = data.mode || 'unknown';
    
    // Clear any previous content
    resultContent.replaceChildren();
    
    // Create result content wrapper
    const resultWrapper = document.createElement('div');
    resultWrapper.className = 'result-content';
    
    // Success message
    const successItem = document.createElement('div');
    successItem.className = 'result-item';
    
    const successHeading = document.createElement('h3');
    successHeading.style.color = 'var(--success-color)';
    successHeading.style.marginBottom = '0.5rem';
    successHeading.textContent = '✅ Generation Successful!';
    
    const successParagraph = document.createElement('p');
    successParagraph.textContent = 'Your system was generated in ';
    
    const modeStrong = document.createElement('strong');
    modeStrong.textContent = mode;
    
    successParagraph.appendChild(modeStrong);
    successParagraph.appendChild(document.createTextNode(' mode.'));
    
    successItem.appendChild(successHeading);
    successItem.appendChild(successParagraph);
    resultWrapper.appendChild(successItem);
    
    // Architecture type
    if (manifest.architecture_type) {
        const archItem = document.createElement('div');
        archItem.className = 'result-item';
        
        const archLabel = document.createElement('strong');
        archLabel.textContent = 'Architecture: ';
        
        const archValue = document.createElement('span');
        archValue.style.color = 'var(--primary-color)';
        archValue.textContent = manifest.architecture_type;
        
        archItem.appendChild(archLabel);
        archItem.appendChild(archValue);
        resultWrapper.appendChild(archItem);
    }
    
    // Plan title
    if (manifest.plan_title) {
        const planItem = document.createElement('div');
        planItem.className = 'result-item';
        
        const planLabel = document.createElement('strong');
        planLabel.textContent = 'Plan Title: ';
        
        const planValue = document.createTextNode(manifest.plan_title);
        
        planItem.appendChild(planLabel);
        planItem.appendChild(planValue);
        resultWrapper.appendChild(planItem);
    }
    
    // Cell count
    if (manifest.cell_count) {
        const cellItem = document.createElement('div');
        cellItem.className = 'result-item';
        
        const cellLabel = document.createElement('strong');
        cellLabel.textContent = 'Generated Cells: ';
        
        const cellValue = document.createTextNode(String(manifest.cell_count));
        
        cellItem.appendChild(cellLabel);
        cellItem.appendChild(cellValue);
        resultWrapper.appendChild(cellItem);
    }
    
    // Output directory
    if (data.manifest_path) {
        const outputItem = document.createElement('div');
        outputItem.className = 'result-item';
        
        const outputLabel = document.createElement('strong');
        outputLabel.textContent = 'Output Directory: ';
        
        const outputCode = document.createElement('code');
        outputCode.style.background = 'var(--bg-tertiary)';
        outputCode.style.padding = '0.25rem 0.5rem';
        outputCode.style.borderRadius = '0.25rem';
        outputCode.textContent = data.output_dir || 'output/';
        
        outputItem.appendChild(outputLabel);
        outputItem.appendChild(outputCode);
        resultWrapper.appendChild(outputItem);
    }
    
    // Notebook plan path
    if (manifest.plan_path) {
        const planPathItem = document.createElement('div');
        planPathItem.className = 'result-item';
        
        const planPathLabel = document.createElement('strong');
        planPathLabel.textContent = 'Notebook Plan: ';
        
        const planPathCode = document.createElement('code');
        planPathCode.style.background = 'var(--bg-tertiary)';
        planPathCode.style.padding = '0.25rem 0.5rem';
        planPathCode.style.borderRadius = '0.25rem';
        planPathCode.style.fontSize = '0.875rem';
        planPathCode.textContent = manifest.plan_path;
        
        planPathItem.appendChild(planPathLabel);
        planPathItem.appendChild(planPathCode);
        resultWrapper.appendChild(planPathItem);
    }
    
    // Generated cells path
    if (manifest.cells_path) {
        const cellsPathItem = document.createElement('div');
        cellsPathItem.className = 'result-item';
        
        const cellsPathLabel = document.createElement('strong');
        cellsPathLabel.textContent = 'Generated Cells: ';
        
        const cellsPathCode = document.createElement('code');
        cellsPathCode.style.background = 'var(--bg-tertiary)';
        cellsPathCode.style.padding = '0.25rem 0.5rem';
        cellsPathCode.style.borderRadius = '0.25rem';
        cellsPathCode.style.fontSize = '0.875rem';
        cellsPathCode.textContent = manifest.cells_path;
        
        cellsPathItem.appendChild(cellsPathLabel);
        cellsPathItem.appendChild(cellsPathCode);
        resultWrapper.appendChild(cellsPathItem);
    }
    
    // Next steps section
    const stepsItem = document.createElement('div');
    stepsItem.className = 'result-item';
    stepsItem.style.marginTop = '1.5rem';
    stepsItem.style.padding = '1rem';
    stepsItem.style.background = 'var(--bg-primary)';
    stepsItem.style.borderRadius = '0.5rem';
    
    const stepsHeading = document.createElement('h4');
    stepsHeading.style.marginBottom = '0.5rem';
    stepsHeading.style.color = 'var(--text-primary)';
    stepsHeading.textContent = '📝 Next Steps:';
    
    const stepsList = document.createElement('ol');
    stepsList.style.marginLeft = '1.5rem';
    stepsList.style.color = 'var(--text-secondary)';
    
    const steps = [
        'Check the output directory for generated artifacts',
        'Review the notebook plan and generated cells',
        'Import the cells into a Jupyter notebook',
        'Customize and run your multi-agent system'
    ];
    
    steps.forEach(stepText => {
        const li = document.createElement('li');
        li.textContent = stepText;
        stepsList.appendChild(li);
    });
    
    stepsItem.appendChild(stepsHeading);
    stepsItem.appendChild(stepsList);
    resultWrapper.appendChild(stepsItem);
    
    // Add export buttons section
    const exportSection = document.createElement('div');
    exportSection.className = 'result-item';
    exportSection.style.marginTop = '1.5rem';
    
    const exportHeading = document.createElement('h4');
    exportHeading.style.marginBottom = '1rem';
    exportHeading.style.color = 'var(--text-primary)';
    exportHeading.textContent = '📥 Available Downloads:';
    
    const exportButtons = document.createElement('div');
    exportButtons.style.display = 'flex';
    exportButtons.style.gap = '0.75rem';
    exportButtons.style.flexWrap = 'wrap';
    
    // Add download buttons for available formats
    const formats = [
        { key: 'notebook_path', label: 'Notebook (.ipynb)', icon: '📓' },
        { key: 'html_path', label: 'HTML', icon: '🌐' },
        { key: 'docx_path', label: 'Word Doc', icon: '📄' },
        { key: 'pdf_path', label: 'PDF', icon: '📕' },
        { key: 'zip_path', label: 'ZIP Bundle', icon: '📦' }
    ];
    
    formats.forEach(format => {
        if (manifest[format.key]) {
            const btn = document.createElement('a');
            btn.className = 'btn btn-secondary';
            btn.href = manifest[format.key];
            btn.download = '';
            btn.style.display = 'inline-flex';
            btn.style.textDecoration = 'none';
            btn.textContent = `${format.icon} ${format.label}`;
            exportButtons.appendChild(btn);
        }
    });
    
    // Add copy result button
    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn btn-secondary';
    copyBtn.textContent = '📋 Copy Result Info';
    copyBtn.onclick = () => {
        const resultText = JSON.stringify(manifest, null, 2);
        navigator.clipboard.writeText(resultText).then(() => {
            const originalText = copyBtn.textContent;
            copyBtn.textContent = '✅ Copied!';
            setTimeout(() => {
                copyBtn.textContent = originalText;
            }, 2000);
        }).catch(err => {
            console.error('Failed to copy:', err);
        });
    };
    exportButtons.appendChild(copyBtn);
    
    exportSection.appendChild(exportHeading);
    exportSection.appendChild(exportButtons);
    resultWrapper.appendChild(exportSection);
    
    // Add to DOM
    resultContent.appendChild(resultWrapper);
    resultCard.style.display = 'block';
    resultCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Show error
function showError(message) {
    hideResults();
    
    // Clear any previous error content
    errorContent.replaceChildren();

    // Build error block safely using DOM APIs
    const wrapper = document.createElement('div');
    wrapper.style.background = 'var(--bg-tertiary)';
    wrapper.style.padding = '1rem';
    wrapper.style.borderRadius = '0.5rem';
    wrapper.style.marginTop = '1rem';

    const messageParagraph = document.createElement('p');
    messageParagraph.style.color = 'var(--text-primary)';
    messageParagraph.style.marginBottom = '0.5rem';
    messageParagraph.textContent = message;

    const helperText = document.createElement('small');
    helperText.style.color = 'var(--text-muted)';
    helperText.textContent = 'Please check your inputs and try again.';

    wrapper.appendChild(messageParagraph);
    wrapper.appendChild(helperText);
    errorContent.appendChild(wrapper);
    
    errorCard.style.display = 'block';
    errorCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Handle form submission
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formData = new FormData(form);
    
    // Collect selected formats
    const formats = [];
    const formatCheckboxes = document.querySelectorAll('input[name="formats"]:checked');
    formatCheckboxes.forEach(cb => formats.push(cb.value));
    
    // Validate at least one format is selected
    if (formats.length === 0) {
        showError('Please select at least one output format.');
        return;
    }
    
    const data = {
        prompt: formData.get('prompt'),
        mode: formData.get('mode'),
        output_dir: formData.get('outputDir'),
        formats: formats
    };
    
    // Add advanced options if specified
    const model = formData.get('model');
    if (model) data.model = model;
    
    const customEndpoint = formData.get('customEndpoint');
    if (customEndpoint && model === 'custom') data.custom_endpoint = customEndpoint;
    
    const preset = formData.get('preset');
    if (preset) data.preset = preset;
    
    const temperature = parseFloat(formData.get('temperature'));
    // Only send temperature if it differs from default (0.7)
    if (!isNaN(temperature) && temperature !== 0.7) data.temperature = temperature;
    
    const maxTokens = formData.get('maxTokens');
    if (maxTokens) data.max_tokens = parseInt(maxTokens);
    
    const agentType = formData.get('agentType');
    if (agentType) data.agent_type = agentType;
    
    const memoryConfig = formData.get('memoryConfig');
    if (memoryConfig) data.memory_config = memoryConfig;
    
    const graphStyle = formData.get('graphStyle');
    if (graphStyle) data.graph_style = graphStyle;
    
    const retrieverType = formData.get('retrieverType');
    if (retrieverType) data.retriever_type = retrieverType;
    
    const documentLoader = formData.get('documentLoader');
    if (documentLoader) data.document_loader = documentLoader;
    
    // Validate prompt length (using Unicode code points)
    if (getCharacterCount(data.prompt) > 5000) {
        showError('Prompt exceeds maximum length of 5000 characters.');
        return;
    }
    
    if (getCharacterCount(data.prompt.trim()) === 0) {
        showError('Please enter a prompt describing your system.');
        return;
    }
    
    // Save to history
    saveToHistory(data);
    
    setLoading(true);
    hideResults();
    
    // Show initial progress
    showProgress(1, 10, 'Validating input...');
    
    // Track progress timeout IDs to clear them if API completes early
    const progressTimeouts = [];
    
    try {
        // Simulate progress updates only if they haven't been overtaken by actual progress
        progressTimeouts.push(setTimeout(() => {
            if (progressPercentage.textContent === '10%') {
                showProgress(2, 25, 'Preparing generation context...');
            }
        }, 500));
        progressTimeouts.push(setTimeout(() => {
            if (parseInt(progressPercentage.textContent) < 50) {
                showProgress(3, 50, 'Invoking LLM...');
            }
        }, 1000));
        
        const response = await fetch('/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
        // Clear any pending simulated progress updates
        progressTimeouts.forEach(id => clearTimeout(id));
        
        showProgress(4, 75, 'Generating artifacts...');
        
        const result = await response.json();
        
        showProgress(5, 90, 'Finalizing outputs...');
        
        if (response.ok && result.success) {
            setTimeout(() => {
                showProgress(6, 100, 'Complete!');
                setTimeout(() => showResult(result), 500);
            }, 300);
        } else {
            // Log detailed error for debugging but show generic message to user
            const serverErrorDetail = (result && (result.error || result.detail)) || '';
            if (serverErrorDetail) {
                console.error('Server error during generation:', serverErrorDetail);
            }
            const errorMsg = 'Generation failed. Please try again or contact support if the problem persists.';
            showError(errorMsg);
        }
    } catch (error) {
        console.error('Generation error:', error);
        showError('Network error: Unable to reach the server. Please ensure the server is running and try again.');
    } finally {
        setLoading(false);
    }
});

// Check health on load
checkHealth();

// Periodically check health
const healthCheckInterval = setInterval(checkHealth, 30000); // Check every 30 seconds

// Cleanup function (can be called when page unloads or component unmounts)
window.addEventListener('beforeunload', () => {
    clearInterval(healthCheckInterval);
});

// History Management
function saveToHistory(data) {
    try {
        const history = JSON.parse(localStorage.getItem('generationHistory') || '[]');
        const promptText = data && typeof data.prompt === 'string' ? data.prompt : String(data.prompt || '');
        const promptCodePoints = Array.from(promptText);
        const isTruncated = promptCodePoints.length > 100;
        const promptPreview = promptCodePoints.slice(0, 100).join('') + (isTruncated ? '...' : '');
        const entry = {
            timestamp: new Date().toISOString(),
            prompt: promptPreview,
            fullPrompt: promptText,
            mode: data.mode,
            model: data.model || 'default',
            fullData: data
        };
        history.unshift(entry);
        // Keep only last 10 entries
        if (history.length > 10) {
            history.pop();
        }
        localStorage.setItem('generationHistory', JSON.stringify(history));
        updateHistoryDisplay();
    } catch (e) {
        console.error('Failed to save to history:', e);
        // Show user-facing notification
        showError('Failed to save generation to history. Your browser storage may be full or disabled.');
    }
}

function loadFromHistory() {
    try {
        return JSON.parse(localStorage.getItem('generationHistory') || '[]');
    } catch (e) {
        console.error('Failed to load history:', e);
        return [];
    }
}

function clearHistory() {
    try {
        localStorage.removeItem('generationHistory');
        updateHistoryDisplay();
        console.log('History cleared');
    } catch (e) {
        console.error('Failed to clear history:', e);
        // Show user-facing notification
        showError('Failed to clear history. Your browser storage may be disabled.');
    }
}

function updateHistoryDisplay() {
    const historyContent = document.getElementById('historyContent');
    const history = loadFromHistory();
    
    if (history.length === 0) {
        historyContent.textContent = '';
        const emptyMessage = document.createElement('p');
        emptyMessage.style.color = 'var(--text-muted)';
        emptyMessage.style.textAlign = 'center';
        emptyMessage.textContent = 'No recent generations';
        historyContent.appendChild(emptyMessage);
        return;
    }
    
    historyContent.textContent = '';
    history.forEach((entry, index) => {
        const item = document.createElement('div');
        item.className = 'history-item';
        item.setAttribute('role', 'button');
        item.setAttribute('tabindex', '0');
        
        const header = document.createElement('div');
        header.className = 'history-item-header';
        
        const time = document.createElement('div');
        time.className = 'history-item-time';
        const date = new Date(entry.timestamp);
        time.textContent = date.toLocaleString();
        
        header.appendChild(time);
        
        const prompt = document.createElement('div');
        prompt.className = 'history-item-prompt';
        prompt.textContent = entry.prompt;
        prompt.title = entry.fullPrompt;
        
        const meta = document.createElement('div');
        meta.className = 'history-item-meta';
        
        const modeTag = document.createElement('span');
        modeTag.className = 'history-tag';
        modeTag.textContent = entry.mode;
        
        const modelTag = document.createElement('span');
        modelTag.className = 'history-tag';
        modelTag.textContent = entry.model;
        
        meta.appendChild(modeTag);
        meta.appendChild(modelTag);
        
        item.appendChild(header);
        item.appendChild(prompt);
        item.appendChild(meta);
        
        // Click to reuse this configuration
        item.addEventListener('click', () => {
            rerunFromHistory(entry);
        });
        
        // Keyboard support
        item.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                rerunFromHistory(entry);
            }
        });
        
        historyContent.appendChild(item);
    });
}

function rerunFromHistory(entry) {
    const data = entry.fullData;
    
    // Fill in the form
    document.getElementById('prompt').value = data.prompt;
    document.getElementById('mode').value = data.mode || 'stub';
    document.getElementById('outputDir').value = data.output_dir || './output/web_generated';
    
    if (data.model) {
        document.getElementById('model').value = data.model;
        // Trigger change event to show/hide custom endpoint
        document.getElementById('model').dispatchEvent(new Event('change'));
    }
    
    if (data.custom_endpoint) {
        document.getElementById('customEndpoint').value = data.custom_endpoint;
    }
    
    if (data.preset) {
        document.getElementById('preset').value = data.preset;
    }
    
    if (data.temperature !== undefined) {
        const tempSlider = document.getElementById('temperature');
        tempSlider.value = data.temperature;
        document.getElementById('tempValue').textContent = data.temperature;
    }
    
    if (data.max_tokens) {
        document.getElementById('maxTokens').value = data.max_tokens;
    }
    
    if (data.agent_type) {
        document.getElementById('agentType').value = data.agent_type;
    }
    
    if (data.memory_config) {
        document.getElementById('memoryConfig').value = data.memory_config;
    }
    
    if (data.graph_style) {
        document.getElementById('graphStyle').value = data.graph_style;
    }
    
    if (data.retriever_type) {
        document.getElementById('retrieverType').value = data.retriever_type;
    }
    
    if (data.document_loader) {
        document.getElementById('documentLoader').value = data.document_loader;
    }
    
    // Restore output formats from history, if available
    if (Array.isArray(data.formats)) {
        const formatCheckboxes = document.querySelectorAll('input[type="checkbox"][name="formats"]');
        formatCheckboxes.forEach((checkbox) => {
            checkbox.checked = data.formats.includes(checkbox.value);
        });
    }
    
    // Scroll to form
    form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    
    // Hide history
    document.getElementById('historyCard').style.display = 'none';
    
    // Show a notification
    const notification = document.createElement('div');
    notification.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--success-color); color: white; padding: 1rem; border-radius: 0.5rem; z-index: 1000; opacity: 1; transition: opacity 0.3s ease; animation: slideDown 0.3s ease;';
    notification.textContent = '✅ Configuration loaded from history';
    document.body.appendChild(notification);
    
    setTimeout(() => {
        // Fade out the notification before removing it
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 2000);
}

// History toggle button
const historyToggleBtn = document.getElementById('historyToggleBtn');
const historyCard = document.getElementById('historyCard');

historyToggleBtn.addEventListener('click', () => {
    const isVisible = historyCard.style.display !== 'none';
    
    if (isVisible) {
        historyCard.style.display = 'none';
    } else {
        updateHistoryDisplay();
        historyCard.style.display = 'block';
        historyCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
});

// Clear history button
const clearHistoryBtn = document.getElementById('clearHistoryBtn');
clearHistoryBtn.addEventListener('click', () => {
    if (confirm('Are you sure you want to clear all history?')) {
        clearHistory();
    }
});

// Initialize history display on load
updateHistoryDisplay();
