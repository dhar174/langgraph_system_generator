// DOM elements
const form = document.getElementById('generateForm');
const promptTextarea = document.getElementById('prompt');
let charCount = document.getElementById('charCount');
const generateBtn = document.getElementById('generateBtn');
const btnText = generateBtn?.querySelector('.btn-text');
const spinner = generateBtn?.querySelector('.spinner');
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
let currentEventSource = null;

// Validation constants
const CHAR_COUNT_MIN = 10;
const CHAR_COUNT_MAX = 5000;
const CHAR_COUNT_WARNING = 4500;

// Advanced options
const advancedToggle = document.getElementById('advancedToggle');
const advancedPanel = document.getElementById('advancedPanel');
const temperatureSlider = document.getElementById('temperature');
const tempValue = document.getElementById('tempValue');
const modelSelect = document.getElementById('model');
const customEndpointGroup = document.getElementById('customEndpointGroup');
const customModelInput = document.getElementById('customModel');

// Theme toggle
const themeToggle = document.getElementById('themeToggle');
const themeIcon = themeToggle.querySelector('.theme-icon');

// Initialize theme from localStorage
const currentTheme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', currentTheme);
themeIcon.textContent = currentTheme === 'dark' ? 'Dark' : 'Light';

// Theme toggle functionality
themeToggle.addEventListener('click', () => {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    themeIcon.textContent = newTheme === 'dark' ? 'Dark' : 'Light';
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
        customModelInput.required = true;
    } else {
        customEndpointGroup.style.display = 'none';
        document.getElementById('customEndpoint').required = false;
        customModelInput.required = false;
    }
});

// Sync HTML attributes with JavaScript constants on page load
if (promptTextarea) {
    promptTextarea.setAttribute('minlength', CHAR_COUNT_MIN);
    promptTextarea.setAttribute('maxlength', CHAR_COUNT_MAX);
}
if (charCount) {
    const charCountMessage = document.getElementById('charCountMessage');
    if (charCountMessage) {
        charCountMessage.innerHTML = `<span id="charCount">0</span> / ${CHAR_COUNT_MAX} characters`;
        // Re-query charCount element after innerHTML replacement
        charCount = document.getElementById('charCount');
    }
}

// Helper to count Unicode characters (code points) for accurate counting
function getCharacterCount(text) {
    return Array.from(text || '').length;
}

function buildArtifactDownloadUrl(path) {
    return `/artifacts?path=${encodeURIComponent(path)}`;
}

function showToast(message, duration = 2000) {
    const notification = document.createElement('div');
    notification.className = 'toast-notification';
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, duration);
}

async function copyTextToClipboard(text, successMessage) {
    try {
        await navigator.clipboard.writeText(text);
        showToast(successMessage);
        return true;
    } catch (err) {
        console.error('Failed to copy:', err);
        showError('Failed to copy to clipboard. Your browser may block clipboard access.');
        return false;
    }
}

function appendLabeledValue(parent, label, value, options = {}) {
    const item = document.createElement('div');
    item.className = 'result-item';

    const strong = document.createElement('strong');
    strong.textContent = `${label}: `;
    item.appendChild(strong);

    const valueNode = options.asCode ? document.createElement('code') : document.createElement('span');
    if (options.color) {
        valueNode.style.color = options.color;
    }
    valueNode.textContent = value;
    item.appendChild(valueNode);

    parent.appendChild(item);
}

// Update character count
promptTextarea.addEventListener('input', () => {
    const count = getCharacterCount(promptTextarea.value);
    charCount.textContent = count;
    
    // Visual feedback for character count
    if (count > CHAR_COUNT_MAX) {
        charCount.style.color = 'var(--error-color)';
        charCount.style.fontWeight = 'bold';
        promptTextarea.classList.add('invalid');
        promptTextarea.classList.remove('valid');
    } else if (count > CHAR_COUNT_WARNING) {
        charCount.style.color = 'var(--warning-color)';
        charCount.style.fontWeight = 'bold';
        promptTextarea.classList.remove('invalid', 'valid');
    } else if (count >= CHAR_COUNT_MIN) {
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
if (outputDirInput) {
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
        // Note: Do not treat ":" as universally invalid; it is allowed on Unix/Mac filesystems.
        const invalidChars = /[<>"|?*\u0000-\u001F]/;
        // Windows reserved names are case-insensitive and forbidden at any directory level.
        // Regex checks each path component separately via split. Filter empty parts from split.
        const windowsReservedNames = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$/i;
        const hasReservedName = value
            .split(/[\\/]/)
            .filter((part) => part.length > 0)
            .some((part) => windowsReservedNames.test(part));
        
        // Robust platform detection (using modern API with fallbacks)
        let isWindowsPlatform = false;
        if (typeof navigator !== 'undefined') {
            const uaDataPlatform =
                navigator.userAgentData && navigator.userAgentData.platform;
            const legacyPlatform = navigator.platform;
            const ua = navigator.userAgent;
            
            // Prefer explicit platform information when available; only fall back to userAgent
            // if neither userAgentData.platform nor navigator.platform provide a usable value.
            const primaryPlatform =
                (typeof uaDataPlatform === 'string' && uaDataPlatform.trim() !== '')
                    ? uaDataPlatform
                    : (typeof legacyPlatform === 'string' && legacyPlatform.trim() !== '')
                        ? legacyPlatform
                        : null;

            if (typeof primaryPlatform === 'string') {
                isWindowsPlatform = primaryPlatform.toLowerCase().includes('win');
            } else if (typeof ua === 'string') {
                const uaTrimmed = ua.trim();
                if (uaTrimmed.length > 0) {
                    // Note: userAgent is used as a final fallback compatibility signal for Windows detection
                    // when explicit platform information is unavailable.
                    isWindowsPlatform = uaTrimmed.toLowerCase().includes('win');
                }
            }
        }
        
        // Disallow colons that are not used as a drive letter designator (e.g. "C:\" or "C:file.txt")
        // on Windows platforms.
        let hasInvalidColonUsage = false;
        if (isWindowsPlatform) {
            const firstColonIndex = value.indexOf(':');
            if (firstColonIndex !== -1) {
                // Accept a single leading "<letter>:" as a valid drive designator.
                const hasDriveLetterPrefix =
                    firstColonIndex === 1 && /^[a-zA-Z]$/.test(value[0]);
                const hasExtraColon = value.indexOf(':', firstColonIndex + 1) !== -1;
                hasInvalidColonUsage = !hasDriveLetterPrefix || hasExtraColon;
            }
        }

        // Determine validation result and provide user feedback
        let validationMessage = '';
        if (invalidChars.test(value)) {
            validationMessage = 'Path contains invalid characters';
        } else if (hasReservedName) {
            validationMessage = 'Path contains reserved Windows filename';
        } else if (hasInvalidColonUsage) {
            validationMessage = 'Invalid colon placement in path';
        }
        
        if (validationMessage) {
            outputDirInput.classList.add('invalid');
            outputDirInput.classList.remove('valid');
            outputDirInput.setAttribute('aria-invalid', 'true');
            outputDirInput.setAttribute('title', validationMessage);
        } else {
            outputDirInput.classList.add('valid');
            outputDirInput.classList.remove('invalid');
            outputDirInput.setAttribute('aria-invalid', 'false');
            outputDirInput.removeAttribute('title');
        }
    });
}

// Trigger initial validation for default or pre-filled value
if (outputDirInput && outputDirInput.value && outputDirInput.value.length > 0) {
    outputDirInput.dispatchEvent(new Event('input'));
}

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
        icon.textContent = '...';
        
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
            icon.textContent = 'OK';
        } else if (Math.abs(percentage - stepPercent) < 15) {
            stepDiv.classList.add('active');
            icon.textContent = '...';
        } else {
            icon.textContent = '...';
        }
    });
}

// Show success result
function showResult(data) {
    hideResults();

    const manifest = data.manifest || {};
    const mode = data.mode || 'unknown';
    const warnings = Array.isArray(manifest.warnings) ? manifest.warnings : [];

    resultContent.replaceChildren();

    const resultWrapper = document.createElement('div');
    resultWrapper.className = 'result-content';

    const successItem = document.createElement('div');
    successItem.className = 'result-item';

    const successHeading = document.createElement('h3');
    successHeading.style.color = 'var(--success-color)';
    successHeading.style.marginBottom = '0.5rem';
    successHeading.textContent = warnings.length > 0
        ? 'Generation Completed With Warnings'
        : 'Generation Successful!';

    const successParagraph = document.createElement('p');
    successParagraph.textContent = `Your system was generated in ${mode} mode.`;

    successItem.appendChild(successHeading);
    successItem.appendChild(successParagraph);
    resultWrapper.appendChild(successItem);

    if (manifest.architecture_type) {
        appendLabeledValue(resultWrapper, 'Architecture', manifest.architecture_type, {
            color: 'var(--primary-color)',
        });
    }

    if (manifest.plan_title) {
        appendLabeledValue(resultWrapper, 'Plan Title', manifest.plan_title);
    }

    if (manifest.cell_count) {
        appendLabeledValue(resultWrapper, 'Generated Cells', String(manifest.cell_count));
    }

    if (data.output_dir) {
        appendLabeledValue(resultWrapper, 'Output Directory', data.output_dir, {
            asCode: true,
        });
    }

    if (warnings.length > 0) {
        const warningItem = document.createElement('div');
        warningItem.className = 'result-item';
        warningItem.style.background = 'var(--bg-primary)';
        warningItem.style.padding = '1rem';
        warningItem.style.borderRadius = '0.5rem';
        warningItem.style.marginTop = '1rem';

        const warningHeading = document.createElement('h4');
        warningHeading.textContent = 'Warnings';
        warningHeading.style.marginBottom = '0.5rem';
        warningItem.appendChild(warningHeading);

        const warningList = document.createElement('ul');
        warnings.forEach((warning) => {
            const item = document.createElement('li');
            item.textContent = warning.message || 'A non-fatal export warning occurred.';
            warningList.appendChild(item);
        });
        warningItem.appendChild(warningList);
        resultWrapper.appendChild(warningItem);
    }

    const exportSection = document.createElement('div');
    exportSection.className = 'result-item';
    exportSection.style.marginTop = '1.5rem';

    const exportHeading = document.createElement('h4');
    exportHeading.style.marginBottom = '1rem';
    exportHeading.style.color = 'var(--text-primary)';
    exportHeading.textContent = 'Available Downloads:';
    exportSection.appendChild(exportHeading);

    const exportButtons = document.createElement('div');
    exportButtons.style.display = 'flex';
    exportButtons.style.gap = '0.75rem';
    exportButtons.style.flexWrap = 'wrap';

    [
        { key: 'notebook_path', label: 'Notebook (.ipynb)' },
        { key: 'html_path', label: 'HTML' },
        { key: 'docx_path', label: 'Word Doc' },
        { key: 'pdf_path', label: 'PDF' },
        { key: 'zip_path', label: 'ZIP Bundle' },
        { key: 'markdown_path', label: 'Markdown (.md)' }
    ].forEach((format) => {
        if (manifest[format.key]) {
            const btn = document.createElement('a');
            btn.className = 'btn btn-secondary';
            btn.href = buildArtifactDownloadUrl(manifest[format.key]);
            btn.download = '';
            btn.style.display = 'inline-flex';
            btn.style.textDecoration = 'none';
            btn.textContent = format.label;
            exportButtons.appendChild(btn);
        }
    });

    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn btn-secondary';
    copyBtn.textContent = 'Copy Result Info';
    copyBtn.addEventListener('click', () => {
        copyTextToClipboard(JSON.stringify(manifest, null, 2), 'Result info copied to clipboard');
    });
    exportButtons.appendChild(copyBtn);

    exportSection.appendChild(exportButtons);
    resultWrapper.appendChild(exportSection);

    resultContent.appendChild(resultWrapper);
    resultCard.style.display = 'block';
    resultCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function extractErrorMessage(payload, fallback = null) {
    if (payload && typeof payload === 'object') {
        if (typeof payload.message === 'string' && payload.message.trim()) {
            return payload.message.trim();
        }
        if (typeof payload.error === 'string' && payload.error.trim()) {
            return payload.error.trim();
        }
        if (payload.detail) {
            if (typeof payload.detail === 'string' && payload.detail.trim()) {
                return payload.detail.trim();
            }
            if (typeof payload.detail === 'object') {
                return extractErrorMessage(payload.detail, fallback);
            }
        }
    }
    if (fallback && typeof fallback === 'object') {
        return extractErrorMessage(fallback, null);
    }
    return 'Generation failed. Please review the server details and try again.';
}

function closeProgressStream() {
    if (currentEventSource) {
        currentEventSource.close();
        currentEventSource = null;
    }
}

// Show error
function showError(message) {
    hideResults();
    errorContent.replaceChildren();

    const wrapper = document.createElement('div');
    wrapper.style.background = 'var(--bg-tertiary)';
    wrapper.style.padding = '1rem';
    wrapper.style.borderRadius = '0.5rem';
    wrapper.style.marginTop = '1rem';

    const messageParagraph = document.createElement('p');
    messageParagraph.style.color = 'var(--text-primary)';
    messageParagraph.style.marginBottom = '0.5rem';
    messageParagraph.textContent = message;

    wrapper.appendChild(messageParagraph);
    errorContent.appendChild(wrapper);

    errorCard.style.display = 'block';
    errorCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function streamGeneration(streamUrl) {
    return new Promise((resolve, reject) => {
        closeProgressStream();
        const eventSource = new EventSource(streamUrl);
        currentEventSource = eventSource;
        let latestErrorDetails = null;
        let streamSettled = false;

        const resolveStream = (payload) => {
            if (streamSettled) {
                return;
            }
            streamSettled = true;
            closeProgressStream();
            resolve(payload);
        };

        const rejectStream = (message) => {
            if (streamSettled) {
                return;
            }
            streamSettled = true;
            closeProgressStream();
            reject(new Error(message));
        };

        eventSource.addEventListener('progress', (event) => {
            const payload = JSON.parse(event.data);
            showProgress(
                payload.node || payload.phase || 'generation',
                payload.percentage || 0,
                payload.message || 'Working...'
            );
        });

        eventSource.addEventListener('log', (event) => {
            const payload = JSON.parse(event.data);
            if (payload.level === 'error') {
                latestErrorDetails = payload.details || {};
            }
        });

        eventSource.addEventListener('complete', (event) => {
            const payload = JSON.parse(event.data);
            resolveStream(payload);
        });

        eventSource.addEventListener('error', (event) => {
            if (event.data) {
                let payload = {};
                try {
                    payload = JSON.parse(event.data);
                } catch (err) {
                    payload = {};
                }
                rejectStream(extractErrorMessage(payload, latestErrorDetails));
                return;
            }

            showProgress(
                'reconnecting',
                parseInt(progressPercentage.textContent, 10) || 12,
                'Connection interrupted. Reconnecting to progress stream...'
            );
        });

        eventSource.onerror = () => {
            if (eventSource.readyState === EventSource.CLOSED) {
                const terminalMessage =
                    latestErrorDetails && Object.keys(latestErrorDetails).length > 0
                        ? extractErrorMessage(latestErrorDetails)
                        : 'Connection to the progress stream was lost. Please try again.';
                rejectStream(terminalMessage);
            }
        };
    });
}

async function startAsyncGeneration(data) {
    const response = await fetch('/generate-async', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    });

    const payload = await response.json();
    if (!response.ok) {
        throw new Error(extractErrorMessage(payload));
    }

    showProgress('queued', 12, 'Generation accepted. Connecting to progress stream...');
    return streamGeneration(payload.stream_url);
}

// Handle form submission
form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(form);
    const formats = [];
    const formatCheckboxes = document.querySelectorAll('input[name="formats"]:checked');
    formatCheckboxes.forEach(cb => formats.push(cb.value));

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

    const model = formData.get('model');
    const customEndpoint = formData.get('customEndpoint');
    const customModel = formData.get('customModel');
    if (model === 'custom') {
        if (customModel) data.model = customModel;
        if (customEndpoint) data.custom_endpoint = customEndpoint;
    } else if (model) {
        data.model = model;
    }

    const temperature = parseFloat(formData.get('temperature'));
    if (!isNaN(temperature) && temperature !== 0.7) data.temperature = temperature;

    const maxTokens = formData.get('maxTokens');
    if (maxTokens) data.max_tokens = parseInt(maxTokens);

    const agentType = formData.get('agentType');
    if (agentType) data.agent_type = agentType;

    if (getCharacterCount(data.prompt) > CHAR_COUNT_MAX) {
        showError(`Prompt exceeds maximum length of ${CHAR_COUNT_MAX} characters.`);
        return;
    }

    if (getCharacterCount(data.prompt.trim()) < CHAR_COUNT_MIN) {
        showError(`Please enter a prompt of at least ${CHAR_COUNT_MIN} characters.`);
        return;
    }

    if (outputDirInput && outputDirInput.classList.contains('invalid')) {
        const errorMsg = outputDirInput.getAttribute('title') || 'Invalid output directory path';
        showError(`Please fix the output directory: ${errorMsg}`);
        outputDirInput.focus();
        return;
    }

    saveToHistory(data);

    setLoading(true);
    hideResults();
    showProgress('validation', 10, 'Validating input...');

    try {
        const result = await startAsyncGeneration(data);
        showResult(result);
    } catch (error) {
        console.error('Generation error:', error);
        showError(error.message || 'Unable to complete generation.');
    } finally {
        closeProgressStream();
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
    const rerunLastBtn = document.getElementById('rerunLastBtn');
    const copyLastPromptBtn = document.getElementById('copyLastPromptBtn');
    const hasHistory = history.length > 0;

    if (rerunLastBtn) {
        rerunLastBtn.disabled = !hasHistory;
    }
    if (copyLastPromptBtn) {
        copyLastPromptBtn.disabled = !hasHistory;
    }
    
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

function copyLastPromptFromHistory() {
    try {
        const rawHistory = typeof localStorage !== 'undefined'
            ? localStorage.getItem('generationHistory')
            : null;

        let entries = [];
        if (rawHistory) {
            try {
                const parsed = JSON.parse(rawHistory);
                if (Array.isArray(parsed)) {
                    entries = parsed;
                }
            } catch (e) {
                console.error('Failed to parse generationHistory from localStorage', e);
            }
        }

        if (!entries.length) {
            const notification = document.createElement('div');
            notification.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--error-color); color: white; padding: 1rem; border-radius: 0.5rem; z-index: 1000; opacity: 1; transition: opacity 0.3s ease; animation: slideDown 0.3s ease;';
            notification.textContent = 'No history entries available to copy';
            document.body.appendChild(notification);

            setTimeout(() => {
                notification.style.opacity = '0';
                setTimeout(() => notification.remove(), 300);
            }, 2000);
            return;
        }

        const lastEntry = entries[entries.length - 1];
        const prompt =
            (lastEntry && lastEntry.fullData && lastEntry.fullData.prompt) ||
            (lastEntry && lastEntry.prompt);

        if (!prompt) {
            const notification = document.createElement('div');
            notification.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--error-color); color: white; padding: 1rem; border-radius: 0.5rem; z-index: 1000; opacity: 1; transition: opacity 0.3s ease; animation: slideDown 0.3s ease;';
            notification.textContent = 'Last history entry has no prompt to copy';
            document.body.appendChild(notification);

            setTimeout(() => {
                notification.style.opacity = '0';
                setTimeout(() => notification.remove(), 300);
            }, 2000);
            return;
        }

        if (typeof copyTextToClipboard === 'function') {
            copyTextToClipboard(prompt);
        } else if (navigator && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            navigator.clipboard.writeText(prompt).catch((err) => {
                console.error('Failed to write prompt to clipboard via navigator.clipboard', err);
            });
        } else {
            // Fallback: temporary textarea
            const textarea = document.createElement('textarea');
            textarea.value = prompt;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
            } catch (err) {
                console.error('Fallback clipboard copy failed', err);
            }
            textarea.remove();
        }

        const notification = document.createElement('div');
        notification.style.cssText = 'position: fixed; top: 20px; right: 20px; background: var(--success-color); color: white; padding: 1rem; border-radius: 0.5rem; z-index: 1000; opacity: 1; transition: opacity 0.3s ease; animation: slideDown 0.3s ease;';
        notification.textContent = 'Last prompt copied from history';
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.style.opacity = '0';
            setTimeout(() => notification.remove(), 300);
        }, 2000);
    } catch (err) {
        console.error('copyLastPromptFromHistory failed', err);
    }
}

function rerunFromHistory(entry) {
    const data = entry.fullData;
    
    // Fill in the form
    document.getElementById('prompt').value = data.prompt;
    document.getElementById('mode').value = data.mode || 'stub';
    document.getElementById('outputDir').value = data.output_dir || './output/web_generated';
    
    if (data.model) {
        const modelSelectElement = document.getElementById('model');
        const optionExists = Array.from(modelSelectElement.options).some((option) => option.value === data.model);
        const hasCustomEndpoint = Boolean(data.custom_endpoint);

        if (optionExists) {
            modelSelectElement.value = data.model;
        } else if (hasCustomEndpoint) {
            modelSelectElement.value = 'custom';
        } else {
            const explicitModelOption = new Option(data.model, data.model);
            modelSelectElement.add(explicitModelOption);
            modelSelectElement.value = data.model;
        }

        modelSelectElement.dispatchEvent(new Event('change'));

        if (!optionExists && hasCustomEndpoint && customModelInput) {
            customModelInput.value = data.model;
        }
    }
    
    if (data.custom_endpoint) {
        document.getElementById('customEndpoint').value = data.custom_endpoint;
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
    notification.textContent = 'Configuration loaded from history';
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

const rerunLastBtn = document.getElementById('rerunLastBtn');
rerunLastBtn.addEventListener('click', () => {
    const history = loadFromHistory();
    if (history.length > 0) {
        rerunFromHistory(history[0]);
    }
});

const copyLastPromptBtn = document.getElementById('copyLastPromptBtn');
copyLastPromptBtn.addEventListener('click', () => {
    copyLastPromptFromHistory();
});

// Initialize history display on load
updateHistoryDisplay();
}
