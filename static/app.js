// DOM Elements
const forecastForm = document.getElementById('forecastForm');
const beachInput = document.getElementById('beachInput');
const loadingSpinner = document.getElementById('loadingSpinner');
const errorContainer = document.getElementById('errorContainer');
const resultsSection = document.getElementById('resultsSection');

// Chart instance
let forecastChart = null;

// Event Listeners
forecastForm.addEventListener('submit', handleForecastSubmit);

// Initialize - hide results on page load
document.addEventListener('DOMContentLoaded', () => {
    resultsSection.classList.add('hidden');
    loadingSpinner.classList.add('hidden');
    errorContainer.classList.add('hidden');
    
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.js';
    document.head.appendChild(script);
});

async function handleForecastSubmit(e) {
    e.preventDefault();
    
    const beach = beachInput.value.trim();
    if (!beach) {
        showError('Please enter a beach name');
        return;
    }
    
    await fetchForecast(beach);
}

async function fetchForecast(beach) {
    // Show loading state
    loadingSpinner.classList.remove('hidden');
    errorContainer.classList.add('hidden');
    resultsSection.classList.add('hidden');
    
    try {
        const response = await fetch('/forecast', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ beach })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to fetch forecast');
        }
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error('Forecast generation failed');
        }
        
        displayResults(data);
    } catch (error) {
        showError(`Error: ${error.message}`);
    } finally {
        loadingSpinner.classList.add('hidden');
    }
}

function displayResults(data) {
    // Display beach info
    document.getElementById('beachTitle').textContent = data.beach_name;
    document.getElementById('descriptionBox').textContent = data.description || 'N/A';
    
    // Display coordinates
    const coords = data.coordinates;
    if (coords) {
        document.getElementById('coordsDisplay').textContent = 
            `Lat: ${coords.latitude.toFixed(4)}, Lon: ${coords.longitude.toFixed(4)}`;
    }
    
    // Display weather data
    const weather = data.weather_data || {};
    document.getElementById('waveHeight').textContent = 
        weather.wave_height_max ? `${weather.wave_height_max.toFixed(2)} m` : 'N/A';
    document.getElementById('wavePeriod').textContent = 
        weather.wave_period_max ? `${weather.wave_period_max.toFixed(1)} s` : 'N/A';
    document.getElementById('windSpeed').textContent = 
        weather.wind_speed_max ? `${weather.wind_speed_max.toFixed(1)} km/h` : 'N/A';
    document.getElementById('windDirection').textContent = 
        weather.wind_direction ? `${Math.round(weather.wind_direction)}°` : 'N/A';
    
    // Display forecast summary
    document.getElementById('forecastSummary').textContent = data.forecast || 'N/A';
    
    // Draw chart if hourly data available
    if (weather.hourly && weather.hourly.time) {
        drawChart(weather.hourly);
    }
    
    // Show results
    resultsSection.classList.remove('hidden');
    
    // Scroll to results
    setTimeout(() => {
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}

function drawChart(hourlyData) {
    const ctx = document.getElementById('forecastChart');
    
    if (!ctx) return;
    
    // Prepare data
    const times = hourlyData.time || [];
    const waveHeights = hourlyData.wave_height || [];
    const windSpeeds = hourlyData.wind_speed || [];
    
    // Limit to first 24 hours
    const maxPoints = Math.min(24, times.length);
    const limitedTimes = times.slice(0, maxPoints).map(t => {
        const date = new Date(t);
        return date.getHours() + ':00';
    });
    const limitedWaves = waveHeights.slice(0, maxPoints);
    const limitedWinds = windSpeeds.slice(0, maxPoints);
    
    // Destroy existing chart
    if (forecastChart) {
        forecastChart.destroy();
    }
    
    // Create new chart
    forecastChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: limitedTimes,
            datasets: [
                {
                    label: 'Wave Height (m)',
                    data: limitedWaves,
                    borderColor: '#00a8e8',
                    backgroundColor: 'rgba(0, 168, 232, 0.1)',
                    tension: 0.4,
                    fill: true,
                    borderWidth: 2,
                    yAxisID: 'y',
                    pointRadius: 3,
                    pointBackgroundColor: '#00a8e8',
                },
                {
                    label: 'Wind Speed (km/h)',
                    data: limitedWinds,
                    borderColor: '#ff6b35',
                    backgroundColor: 'rgba(255, 107, 53, 0.1)',
                    tension: 0.4,
                    fill: true,
                    borderWidth: 2,
                    yAxisID: 'y1',
                    pointRadius: 3,
                    pointBackgroundColor: '#ff6b35',
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#b0c4ff',
                        font: {
                            size: 12,
                        }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(10, 14, 39, 0.8)',
                    titleColor: '#e8f0ff',
                    bodyColor: '#b0c4ff',
                    borderColor: '#2a3050',
                    borderWidth: 1,
                    padding: 12,
                    titleFont: {
                        size: 13,
                        weight: 'bold'
                    },
                    bodyFont: {
                        size: 12
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(42, 48, 80, 0.3)',
                    },
                    ticks: {
                        color: '#b0c4ff',
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: {
                        color: 'rgba(42, 48, 80, 0.3)',
                    },
                    ticks: {
                        color: '#00a8e8',
                    },
                    title: {
                        display: true,
                        text: 'Wave Height (m)',
                        color: '#00a8e8',
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: {
                        drawOnChartArea: false,
                    },
                    ticks: {
                        color: '#ff6b35',
                    },
                    title: {
                        display: true,
                        text: 'Wind Speed (km/h)',
                        color: '#ff6b35',
                    }
                }
            }
        }
    });
}

function showError(message) {
    errorContainer.textContent = message;
    errorContainer.classList.remove('hidden');
}
