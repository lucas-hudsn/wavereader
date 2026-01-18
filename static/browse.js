// DOM Elements
const stateSelect = document.getElementById('stateSelect');
const breakSelect = document.getElementById('breakSelect');
const loadingSpinner = document.getElementById('loadingSpinner');
const errorContainer = document.getElementById('errorContainer');
const breakDetails = document.getElementById('breakDetails');

// Initialize
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
    } catch (error) {
        showError('Failed to load states');
    }
}

async function handleStateChange() {
    const state = stateSelect.value;

    // Reset break select
    breakSelect.innerHTML = '<option value="">-- Choose a surf break --</option>';
    breakSelect.disabled = true;
    breakDetails.classList.add('hidden');
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

async function handleBreakChange() {
    const breakName = breakSelect.value;

    breakDetails.classList.add('hidden');
    errorContainer.classList.add('hidden');

    if (!breakName) return;

    loadingSpinner.classList.remove('hidden');

    try {
        const response = await fetch(`/api/break/${encodeURIComponent(breakName)}`);
        const data = await response.json();

        if (data.error) {
            showError(data.error);
            return;
        }

        displayBreakDetails(data);
    } catch (error) {
        showError('Failed to load break details');
    } finally {
        loadingSpinner.classList.add('hidden');
    }
}

function displayBreakDetails(data) {
    document.getElementById('breakName').textContent = data.name;
    document.getElementById('breakDescription').textContent = data.description || 'No description available';
    document.getElementById('breakState').textContent = data.state || '-';

    if (data.latitude && data.longitude) {
        document.getElementById('breakCoords').textContent =
            `${data.latitude.toFixed(4)}, ${data.longitude.toFixed(4)}`;
    } else {
        document.getElementById('breakCoords').textContent = '-';
    }

    document.getElementById('breakWaveDir').textContent = capitalize(data.wave_direction) || '-';
    document.getElementById('breakBottom').textContent = capitalize(data.bottom_type) || '-';
    document.getElementById('breakType').textContent = capitalize(data.break_type) || '-';
    document.getElementById('breakSkill').textContent = capitalize(data.skill_level) || '-';

    document.getElementById('breakWind').textContent = data.ideal_wind || '-';
    document.getElementById('breakTide').textContent = data.ideal_tide || '-';
    document.getElementById('breakSwell').textContent = data.ideal_swell_size || '-';

    breakDetails.classList.remove('hidden');

    setTimeout(() => {
        breakDetails.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}

function capitalize(str) {
    if (!str) return str;
    return str.charAt(0).toUpperCase() + str.slice(1);
}

function showError(message) {
    errorContainer.textContent = message;
    errorContainer.classList.remove('hidden');
}
