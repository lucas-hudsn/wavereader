const loadingSpinner = document.getElementById('loadingSpinner');
const errorContainer = document.getElementById('errorContainer');
const breakDetails = document.getElementById('breakDetails');
const forecastLoading = document.getElementById('forecastLoading');
const forecastContent = document.getElementById('forecastContent');
const forecastError = document.getElementById('forecastError');
const chartLoading = document.getElementById('chartLoading');
const chartContainer = document.getElementById('chartContainer');

const pathParts = window.location.pathname.split('/').filter(p => p);
const state = pathParts[0];
const breakName = decodeURIComponent(pathParts[1]);

console.log('URL path:', window.location.pathname);
console.log('State:', state, 'Break:', breakName);

document.addEventListener('DOMContentLoaded', () => {
    if (state && breakName) {
        console.log('Loading break:', breakName);
        loadBreakDetails();
    } else {
        showError('Invalid break URL');
    }
});

async function loadBreakDetails() {
    loadingSpinner.classList.remove('hidden');
    breakDetails.classList.add('hidden');
    errorContainer.classList.add('hidden');

    try {
        const response = await fetch(`/api/break/${encodeURIComponent(breakName)}`);
        const data = await response.json();

        loadingSpinner.classList.add('hidden');

        if (data.error) {
            showError(data.error);
            return;
        }

        displayBreakDetails(data);

        if (data.weather_data && data.weather_data.hourly) {
            renderChart(data.weather_data.hourly);
            chartContainer.classList.remove('hidden');
        }

        if (data.forecast) {
            forecastContent.innerHTML = formatForecast(data.forecast);
            forecastContent.classList.remove('hidden');
        } else {
            forecastError.textContent = 'Unable to generate forecast';
            forecastError.classList.remove('hidden');
        }
    } catch (error) {
        loadingSpinner.classList.add('hidden');
        showError('Failed to load break details');
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
}

function renderChart(hourlyData) {
    const swellChart = document.getElementById('swellChart');
    const windChart = document.getElementById('windChart');
    const chartTimes = document.getElementById('chartTimes');

    swellChart.innerHTML = '';
    windChart.innerHTML = '';
    chartTimes.innerHTML = '';

    const times = hourlyData.time || [];
    const waveHeights = hourlyData.wave_height || [];
    const windSpeeds = hourlyData.wind_speed || [];
    const windDirections = hourlyData.wind_direction || [];

    const dailyDataPoints = [];
    for (let day = 0; day < 7; day++) {
        const startIdx = day * 24;
        const endIdx = Math.min(startIdx + 24, times.length);

        if (startIdx >= times.length) break;

        const dayWaves = waveHeights.slice(startIdx, endIdx).filter(v => v != null);
        const dayWinds = windSpeeds.slice(startIdx, endIdx).filter(v => v != null);
        const dayWindDirs = windDirections.slice(startIdx, endIdx).filter(v => v != null);

        dailyDataPoints.push({
            time: times[startIdx],
            waveHeight: dayWaves.length > 0 ? Math.max(...dayWaves) : null,
            avgWindSpeed: dayWinds.length > 0 ? dayWinds.reduce((a, b) => a + b) / dayWinds.length : null,
            maxWindSpeed: dayWinds.length > 0 ? Math.max(...dayWinds) : null,
            windDir: dayWindDirs.length > 0 ? dayWindDirs[Math.floor(dayWindDirs.length / 2)] : null
        });
    }

    const maxWaveHeight = Math.max(...dailyDataPoints.map(d => d.waveHeight).filter(v => v != null), 1);
    const maxWindSpeed = Math.max(...dailyDataPoints.map(d => d.maxWindSpeed).filter(v => v != null), 1);

    renderSwellLineChart(swellChart, dailyDataPoints, maxWaveHeight);
    renderWindArrows(windChart, dailyDataPoints, maxWindSpeed);

    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    dailyDataPoints.forEach(data => {
        const date = new Date(data.time);
        const dayLabel = dayNames[date.getDay()];
        const timeEl = document.createElement('div');
        timeEl.className = 'chart-time';
        timeEl.textContent = dayLabel;
        chartTimes.appendChild(timeEl);
    });
}

function renderSwellLineChart(container, data, maxHeight) {
    const tooltip = document.createElement('div');
    tooltip.className = 'chart-tooltip';
    container.appendChild(tooltip);

    const height = 100;
    const padding = { top: 15, bottom: 15 };
    const chartHeight = height - padding.top - padding.bottom;

    const points = data.map((d, i) => {
        const x = (i / (data.length - 1)) * 100;
        const normalizedValue = d.waveHeight != null ? d.waveHeight / maxHeight : 0;
        const y = padding.top + chartHeight - (normalizedValue * chartHeight);
        return { x, y, value: d.waveHeight, time: d.time };
    });

    const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
    const areaPath = `${linePath} L ${points[points.length - 1].x} ${height} L ${points[0].x} ${height} Z`;

    let svg = `<svg viewBox="0 0 100 ${height}" preserveAspectRatio="none">`;
    svg += `<path class="swell-area" d="${areaPath}"/>`;
    svg += `<path class="swell-line" d="${linePath}"/>`;

    points.forEach((p, i) => {
        svg += `<circle class="swell-point" cx="${p.x}" cy="${p.y}" r="2" data-index="${i}" data-value="${p.value}" data-time="${p.time}"/>`;
    });

    svg += '</svg>';

    const svgContainer = document.createElement('div');
    svgContainer.style.width = '100%';
    svgContainer.style.height = '100%';
    svgContainer.innerHTML = svg;
    container.appendChild(svgContainer);

    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    svgContainer.querySelectorAll('.swell-point').forEach(point => {
        point.addEventListener('mouseenter', (e) => {
            const value = e.target.dataset.value;
            const time = new Date(e.target.dataset.time);
            const dayName = dayNames[time.getDay()];
            const dateStr = `${time.getDate()}/${time.getMonth() + 1}`;
            tooltip.textContent = `${dayName} ${dateStr} - Max ${parseFloat(value).toFixed(1)}m`;
            tooltip.classList.add('visible');

            const rect = container.getBoundingClientRect();
            const cx = parseFloat(e.target.getAttribute('cx'));
            const cy = parseFloat(e.target.getAttribute('cy'));
            tooltip.style.left = `${(cx / 100) * rect.width}px`;
            tooltip.style.top = `${(cy / 100) * rect.height - 30}px`;
        });

        point.addEventListener('mouseleave', () => {
            tooltip.classList.remove('visible');
        });
    });
}

function renderWindArrows(container, data, maxSpeed) {
    const tooltip = document.createElement('div');
    tooltip.className = 'chart-tooltip';
    container.style.position = 'relative';
    container.appendChild(tooltip);

    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    data.forEach((d, i) => {
        const windBar = document.createElement('div');
        windBar.className = 'wind-bar';

        const speedRatio = d.avgWindSpeed != null ? d.avgWindSpeed / maxSpeed : 0;
        const arrowSize = 16 + (speedRatio * 24);
        const heightPct = 25 + (speedRatio * 70);
        const arrowRotation = d.windDir != null ? d.windDir : 0;
        const date = new Date(d.time);
        const dayLabel = `${dayNames[date.getDay()]} ${date.getDate()}/${date.getMonth() + 1}`;

        windBar.innerHTML = `
            <div class="wind-arrow-container" style="height: ${heightPct}%;">
                <span class="wind-arrow" style="font-size: ${arrowSize}px; transform: rotate(${arrowRotation}deg);"
                      data-speed="${d.avgWindSpeed}" data-dir="${d.windDir}" data-day="${dayLabel}">↓</span>
            </div>
        `;

        windBar.addEventListener('mouseenter', (e) => {
            const arrow = windBar.querySelector('.wind-arrow');
            const speed = arrow.dataset.speed;
            const dir = arrow.dataset.dir;
            const day = arrow.dataset.day;
            const dirLabel = getWindDirection(parseFloat(dir));
            tooltip.textContent = `${day} - Avg ${Math.round(speed)} km/h ${dirLabel}`;
            tooltip.classList.add('visible');

            const rect = container.getBoundingClientRect();
            const barRect = windBar.getBoundingClientRect();
            tooltip.style.left = `${barRect.left - rect.left + barRect.width / 2}px`;
            tooltip.style.top = '-25px';
        });

        windBar.addEventListener('mouseleave', () => {
            tooltip.classList.remove('visible');
        });

        container.appendChild(windBar);
    });
}

function getWindDirection(degrees) {
    if (degrees == null) return '';
    const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
    const index = Math.round(degrees / 45) % 8;
    return directions[index];
}

function formatForecast(text) {
    return text
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>')
        .replace(/^(\d+\.)/gm, '<br>$1');
}

function capitalize(str) {
    if (!str) return str;
    return str.charAt(0).toUpperCase() + str.slice(1);
}

function showError(message) {
    errorContainer.textContent = message;
    errorContainer.classList.remove('hidden');
}
