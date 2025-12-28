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
    const data = {
        prompt: formData.get('prompt'),
        mode: formData.get('mode'),
        output_dir: formData.get('outputDir')
    };
    
    // Validate prompt length (using Unicode code points)
    if (getCharacterCount(data.prompt) > 5000) {
        showError('Prompt exceeds maximum length of 5000 characters.');
        return;
    }
    
    if (data.prompt.trim().length === 0) {
        showError('Please enter a prompt describing your system.');
        return;
    }
    
    setLoading(true);
    hideResults();
    
    try {
        const response = await fetch('/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            showResult(result);
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
