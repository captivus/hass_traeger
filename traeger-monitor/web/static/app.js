// Ultra-simple Traeger Monitor JS - ~80 lines
let chartData = null;

async function updateCurrent() {
    const resp = await fetch('/api/current');
    if (!resp.ok) return;
    const data = await resp.json();
    
    // Update fixed temps
    document.getElementById('grill-temp').textContent = data.grill_temp || '--';
    document.getElementById('grill-set').textContent = data.grill_set || '--';
    document.getElementById('ambient-temp').textContent = data.ambient || '--';
    document.getElementById('pellet-level').textContent = data.pellet_level || '--';
    
    // Update probe cards
    const container = document.getElementById('probe-cards');
    container.innerHTML = '';
    
    for (const probe of (data.probes || [])) {
        const card = document.createElement('div');
        card.className = 'temp-card';
        card.innerHTML = `
            <h3>Probe ${probe.channel}</h3>
            <div class="temp">${probe.temp || '--'}</div>
            <div class="target">Target: ${probe.target || '--'}°F</div>
            ${probe.battery ? `<div class="battery">Battery: ${probe.battery}%</div>` : ''}
            <div class="prediction" id="prediction-${probe.channel}">Calculating...</div>
        `;
        container.appendChild(card);
        
        // Fetch prediction if we have cook_id and probe data
        if (data.cook_id && probe.temp && probe.target && probe.temp < probe.target) {
            try {
                const predResp = await fetch(`/api/predict/${data.cook_id}/${probe.channel}`);
                const predData = await predResp.json();
                const predElement = document.getElementById(`prediction-${probe.channel}`);
                
                if (predData.error) {
                    predElement.textContent = 'No prediction';
                    predElement.style.color = '#666';
                } else {
                    predElement.textContent = `${predData.minutes_to_target} min to target`;
                    predElement.style.color = '#d32f2f';
                    predElement.style.fontWeight = 'bold';
                }
            } catch (e) {
                document.getElementById(`prediction-${probe.channel}`).textContent = 'Prediction error';
            }
        } else {
            document.getElementById(`prediction-${probe.channel}`).textContent = probe.temp >= probe.target ? 'Target reached!' : '';
        }
    }
}

async function updateChart() {
    const hours = document.getElementById('time-range').value;
    const resp = await fetch(`/api/history/${hours}`);
    if (!resp.ok) return;
    
    chartData = await resp.json();
    if (!chartData.length) return;
    
    const times = chartData.map(d => d.timestamp);
    const traces = [
        {x: times, y: chartData.map(d => d.grill_temp), name: 'Grill', line: {color: 'red', width: 3}},
        {x: times, y: chartData.map(d => d.grill_set), name: 'Grill Target', line: {color: 'red', width: 1, dash: 'dot'}},
        {x: times, y: chartData.map(d => d.ambient), name: 'Ambient', line: {color: 'green', width: 1}}
    ];
    
    // Add probe traces
    const maxProbes = 4;
    const colors = ['blue', 'purple', 'orange', 'brown'];
    
    for (let i = 0; i < maxProbes; i++) {
        const temps = chartData.map(d => d.probes?.[i]?.temp || null);
        const targets = chartData.map(d => d.probes?.[i]?.target || null);
        
        if (temps.some(t => t !== null)) {
            traces.push({
                x: times, y: temps, name: `Probe ${i+1}`,
                line: {color: colors[i], width: 2}
            });
            traces.push({
                x: times, y: targets, name: `Probe ${i+1} Target`,
                line: {color: colors[i], width: 1, dash: 'dot'}
            });
        }
    }
    
    Plotly.newPlot('chart', traces, {
        title: 'Temperature History',
        xaxis: {title: 'Time'},
        yaxis: {title: 'Temperature (°F)'},
        height: 400
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await updateCurrent();
    await updateChart();
    setInterval(updateCurrent, 30000);  // Update temps every 30s
    setInterval(updateChart, 120000);   // Update chart every 2m
});