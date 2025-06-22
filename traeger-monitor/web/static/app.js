// Traeger Monitor Frontend

let currentData = null;
let historyData = [];

// Update current temperature display
async function updateCurrent() {
    try {
        const response = await fetch('/api/current');
        const data = await response.json();
        
        if (response.ok) {
            currentData = data;
            
            // Update temperature displays
            updateTemp('grill-temp', data.grill_temp);
            updateTemp('grill-set', data.grill_set);
            updateTemp('probe-temp', data.probe_temp);
            updateTemp('probe-set', data.probe_set);
            updateTemp('ambient-temp', data.ambient);
            updateTemp('pellet-level', data.pellet_level);
            
            // Update status
            const status = data.connected ? ' Connected' : 'L Disconnected';
            document.getElementById('status').textContent = status;
            
            // Update last update time
            const now = new Date();
            document.getElementById('last-update').textContent = 
                `Last update: ${now.toLocaleTimeString()}`;
        }
    } catch (error) {
        console.error('Error fetching current data:', error);
        document.getElementById('status').textContent = 'L Error';
    }
}

// Update temperature display with proper formatting
function updateTemp(elementId, value) {
    const element = document.getElementById(elementId);
    if (element) {
        if (value !== null && value !== undefined) {
            element.textContent = elementId.includes('level') ? value : `${value}°F`;
        } else {
            element.textContent = '--';
        }
    }
}

// Update history chart
async function updateHistory() {
    const hours = document.getElementById('history-hours').value;
    
    try {
        const response = await fetch(`/api/history/${hours}`);
        historyData = await response.json();
        
        if (response.ok && historyData.length > 0) {
            drawChart();
        }
    } catch (error) {
        console.error('Error fetching history:', error);
    }
}

// Draw temperature chart using Plotly
function drawChart() {
    const timestamps = historyData.map(d => d.timestamp);
    
    const traces = [
        {
            x: timestamps,
            y: historyData.map(d => d.grill_temp),
            name: 'Grill Temp',
            type: 'scatter',
            mode: 'lines',
            line: { color: 'red', width: 3 }
        },
        {
            x: timestamps,
            y: historyData.map(d => d.grill_set),
            name: 'Grill Target',
            type: 'scatter',
            mode: 'lines',
            line: { color: 'orange', width: 2, dash: 'dash' }
        }
    ];
    
    // Add probe data if available
    if (historyData.some(d => d.probe_temp !== null)) {
        traces.push({
            x: timestamps,
            y: historyData.map(d => d.probe_temp),
            name: 'Probe Temp',
            type: 'scatter',
            mode: 'lines',
            line: { color: 'blue', width: 2 }
        });
        
        traces.push({
            x: timestamps,
            y: historyData.map(d => d.probe_set),
            name: 'Probe Target',
            type: 'scatter',
            mode: 'lines',
            line: { color: 'lightblue', width: 1, dash: 'dot' }
        });
    }
    
    // Add ambient temperature
    traces.push({
        x: timestamps,
        y: historyData.map(d => d.ambient),
        name: 'Ambient',
        type: 'scatter',
        mode: 'lines',
        line: { color: 'green', width: 1 }
    });
    
    const layout = {
        title: 'Temperature History',
        xaxis: {
            title: 'Time',
            type: 'date'
        },
        yaxis: {
            title: 'Temperature (°F)'
        },
        height: 400,
        margin: { l: 50, r: 50, t: 50, b: 50 }
    };
    
    Plotly.newPlot('temp-chart', traces, layout);
}

// Initialize and start updates
async function init() {
    await updateCurrent();
    await updateHistory();
    
    // Update current temps every 30 seconds
    setInterval(updateCurrent, 30000);
    
    // Update history every 2 minutes
    setInterval(updateHistory, 120000);
}

// Start when page loads
document.addEventListener('DOMContentLoaded', init);