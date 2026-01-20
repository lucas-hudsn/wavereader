const stateSelect = document.getElementById('stateSelect');
const breakSelect = document.getElementById('breakSelect');
const loadingSpinner = document.getElementById('loadingSpinner');
const errorContainer = document.getElementById('errorContainer');

document.addEventListener('DOMContentLoaded', () => {
    loadStates();
    stateSelect.addEventListener('change', handleStateChange);
    breakSelect.addEventListener('change', handleBreakChange);
});

async function loadStates() {
    try {
        const response = await fetch('/api/states');
        const data = await response.json();

        if (data.error) {
            showError(data.error);
            return;
        }

        data.states.forEach(state => {
            const option = document.createElement('option');
            option.value = state;
            option.textContent = state;
            stateSelect.appendChild(option);
        });

        loadingSpinner.classList.add('hidden');
    } catch (error) {
        showError('Failed to load states');
    }
}

async function handleStateChange() {
    const state = stateSelect.value;

    breakSelect.innerHTML = '<option value="">-- Choose a surf break --</option>';
    breakSelect.disabled = true;
    breakSelect.value = '';
    errorContainer.classList.add('hidden');

    if (!state) return;

    loadingSpinner.classList.remove('hidden');

    try {
        const response = await fetch(`/api/breaks/${encodeURIComponent(state)}`);
        const data = await response.json();

        if (data.error) {
            showError(data.error);
            return;
        }

        data.breaks.forEach(breakName => {
            const option = document.createElement('option');
            option.value = breakName;
            option.textContent = breakName;
            breakSelect.appendChild(option);
        });

        breakSelect.disabled = false;
    } catch (error) {
        showError('Failed to load surf breaks');
    } finally {
        loadingSpinner.classList.add('hidden');
    }
}

function handleBreakChange() {
    const breakName = breakSelect.value;
    const state = stateSelect.value;

    if (!breakName || !state) return;

    window.location.href = `/${encodeURIComponent(state)}/${encodeURIComponent(breakName)}`;
}

function showError(message) {
    loadingSpinner.classList.add('hidden');
    errorContainer.textContent = message;
    errorContainer.classList.remove('hidden');
}
