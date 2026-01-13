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

// Helper to count Unicode characters (code points) for accurate counting
function getCharacterCount(text) {
    return Array.from(text || '').length;
}

// Update character count
promptTextarea.addEventListener('input', () => {
    const count = getCharacterCount(promptTextarea.value);
    charCount.textContent = count;
    
    if (count > 5000) {
        charCount.style.color = 'var(--error-color)';
    } else {
        charCount.style.color = 'var(--text-muted)';
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

// Show progress with steps
function showProgress(step, percentage, message) {
    hideResults();
    progressCard.style.display = 'block';
    progressFill.style.width = percentage + '%';
    progressPercentage.textContent = percentage + '%';
    progressText.textContent = message;
    
    // Update steps display
    const steps = [
        { text: 'Validating input', percent: 10 },
        { text: 'Preparing generation context', percent: 25 },
        { text: 'Invoking LLM', percent: 50 },
        { text: 'Generating artifacts', percent: 75 },
        { text: 'Finalizing outputs', percent: 90 },
        { text: 'Complete', percent: 100 }
    ];
    
    progressSteps.innerHTML = '';
    steps.forEach((s, index) => {
        const stepDiv = document.createElement('div');
        stepDiv.className = 'progress-step';
        
        if (percentage >= s.percent) {
            stepDiv.classList.add('complete');
        } else if (Math.abs(percentage - s.percent) < 15) {
            stepDiv.classList.add('active');
        }
        
        const icon = document.createElement('span');
        icon.className = 'step-icon';
        icon.textContent = percentage >= s.percent ? '✅' : '⏳';
        
        const text = document.createElement('span');
        text.className = 'step-text';
        text.textContent = s.text;
        
        stepDiv.appendChild(icon);
        stepDiv.appendChild(text);
        progressSteps.appendChild(stepDiv);
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
    
    const data = {
        prompt: formData.get('prompt'),
        mode: formData.get('mode'),
        output_dir: formData.get('outputDir')
    };
    
    // Add formats if any selected
    if (formats.length > 0) {
        data.formats = formats;
    }
    
    // Add advanced options if specified
    const model = formData.get('model');
    if (model) data.model = model;
    
    const temperature = parseFloat(formData.get('temperature'));
    if (!isNaN(temperature)) data.temperature = temperature;
    
    const maxTokens = formData.get('maxTokens');
    if (maxTokens) data.max_tokens = parseInt(maxTokens);
    
    const agentType = formData.get('agentType');
    if (agentType) data.agent_type = agentType;
    
    const memoryConfig = formData.get('memoryConfig');
    if (memoryConfig) data.memory_config = memoryConfig;
    
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
    
    try {
        // Simulate progress updates
        setTimeout(() => showProgress(2, 25, 'Preparing generation context...'), 500);
        setTimeout(() => showProgress(3, 50, 'Invoking LLM...'), 1000);
        
        const response = await fetch('/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
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
        const entry = {
            timestamp: new Date().toISOString(),
            prompt: data.prompt.substring(0, 100) + (data.prompt.length > 100 ? '...' : ''),
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
    } catch (e) {
        console.error('Failed to save to history:', e);
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
    localStorage.removeItem('generationHistory');
    console.log('History cleared');
}
