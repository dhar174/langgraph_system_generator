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

// Update character count
promptTextarea.addEventListener('input', () => {
    const count = promptTextarea.value.length;
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
    const prompt = data.prompt || '';
    
    let html = '<div class="result-content">';
    
    // Success message
    html += '<div class="result-item">';
    html += '<h3 style="color: var(--success-color); margin-bottom: 0.5rem;">✅ Generation Successful!</h3>';
    html += `<p>Your system was generated in <strong>${mode}</strong> mode.</p>`;
    html += '</div>';
    
    // Manifest details
    if (manifest.architecture_type) {
        html += '<div class="result-item">';
        html += '<strong>Architecture:</strong> ';
        html += `<span style="color: var(--primary-color)">${manifest.architecture_type}</span>`;
        html += '</div>';
    }
    
    if (manifest.plan_title) {
        html += '<div class="result-item">';
        html += '<strong>Plan Title:</strong> ';
        html += manifest.plan_title;
        html += '</div>';
    }
    
    if (manifest.cell_count) {
        html += '<div class="result-item">';
        html += '<strong>Generated Cells:</strong> ';
        html += manifest.cell_count;
        html += '</div>';
    }
    
    // Output location
    if (data.manifest_path) {
        html += '<div class="result-item">';
        html += '<strong>Output Directory:</strong> ';
        html += `<code style="background: var(--bg-tertiary); padding: 0.25rem 0.5rem; border-radius: 0.25rem;">${data.output_dir || 'output/'}</code>`;
        html += '</div>';
    }
    
    // File paths
    if (manifest.plan_path) {
        html += '<div class="result-item">';
        html += '<strong>Notebook Plan:</strong> ';
        html += `<code style="background: var(--bg-tertiary); padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.875rem;">${manifest.plan_path}</code>`;
        html += '</div>';
    }
    
    if (manifest.cells_path) {
        html += '<div class="result-item">';
        html += '<strong>Generated Cells:</strong> ';
        html += `<code style="background: var(--bg-tertiary); padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.875rem;">${manifest.cells_path}</code>`;
        html += '</div>';
    }
    
    // Instructions
    html += '<div class="result-item" style="margin-top: 1.5rem; padding: 1rem; background: var(--bg-primary); border-radius: 0.5rem;">';
    html += '<h4 style="margin-bottom: 0.5rem; color: var(--text-primary);">📝 Next Steps:</h4>';
    html += '<ol style="margin-left: 1.5rem; color: var(--text-secondary);">';
    html += '<li>Check the output directory for generated artifacts</li>';
    html += '<li>Review the notebook plan and generated cells</li>';
    html += '<li>Import the cells into a Jupyter notebook</li>';
    html += '<li>Customize and run your multi-agent system</li>';
    html += '</ol>';
    html += '</div>';
    
    html += '</div>';
    
    resultContent.innerHTML = html;
    resultCard.style.display = 'block';
    resultCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Show error
function showError(message) {
    hideResults();
    
    errorContent.innerHTML = `
        <div style="background: var(--bg-tertiary); padding: 1rem; border-radius: 0.5rem; margin-top: 1rem;">
            <p style="color: var(--text-primary); margin-bottom: 0.5rem;">${message}</p>
            <small style="color: var(--text-muted);">Please check your inputs and try again.</small>
        </div>
    `;
    
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
    
    // Validate prompt length
    if (data.prompt.length > 5000) {
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
            const errorMsg = result.error || result.detail || 'Generation failed. Please try again.';
            showError(errorMsg);
        }
    } catch (error) {
        console.error('Generation error:', error);
        showError(`Network error: ${error.message}. Please ensure the server is running.`);
    } finally {
        setLoading(false);
    }
});

// Check health on load
checkHealth();

// Periodically check health
setInterval(checkHealth, 30000); // Check every 30 seconds
