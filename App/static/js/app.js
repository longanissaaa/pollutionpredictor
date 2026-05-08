// =========================================================
// 1. GLOBAL MATH & COLOR ENGINE (Must be at the top)
// =========================================================

function calculateTrueEPA_AQI(c, pollutant) {
    const calc = (val, cLow, cHigh, iLow, iHigh) => Math.round(((iHigh - iLow) / (cHigh - cLow)) * (val - cLow) + iLow);
    
    if (pollutant === 'PM25') {
        let v = Math.floor(c * 10) / 10;
        if (v <= 12.0) return calc(v, 0, 12.0, 0, 50);
        if (v <= 35.4) return calc(v, 12.1, 35.4, 51, 100);
        if (v <= 55.4) return calc(v, 35.5, 55.4, 101, 150);
        if (v <= 150.4) return calc(v, 55.5, 150.4, 151, 200);
        if (v <= 250.4) return calc(v, 150.5, 250.4, 201, 300);
        // NEW: Split the 301-500 range
        if (v <= 350.4) return calc(v, 250.5, 350.4, 301, 400);
        return calc(v, 350.5, 500.4, 401, 500);
    }
    
    if (pollutant === 'O3') {
        // Assuming 'c' is in µg/m³ from OpenWeather; ~0.51 converts it to ppb
        let v = Math.floor(c * 0.51); 
        if (v <= 54) return calc(v, 0, 54, 0, 50);           // 8-hr
        if (v <= 70) return calc(v, 55, 70, 51, 100);        // 8-hr
        if (v <= 85) return calc(v, 71, 85, 101, 150);       // 8-hr
        if (v <= 105) return calc(v, 86, 105, 151, 200);     // 8-hr
        if (v <= 200) return calc(v, 106, 200, 201, 300);    // 8-hr
        // NEW: Map to the 1-hr O3 bounds for extreme pollution
        if (v <= 504) return calc(v, 405, 504, 301, 400);    // 1-hr bounds
        return calc(v, 505, 604, 401, 500);                  // 1-hr bounds
    }
    
    if (pollutant === 'PM10') {
        let v = Math.floor(c);
        if (v <= 54) return calc(v, 0, 54, 0, 50);
        if (v <= 154) return calc(v, 55, 154, 51, 100);
        if (v <= 254) return calc(v, 155, 254, 101, 150);
        if (v <= 354) return calc(v, 255, 354, 151, 200);
        if (v <= 424) return calc(v, 355, 424, 201, 300);
        // NEW: Split the 301-500 range
        if (v <= 504) return calc(v, 425, 504, 301, 400);
        return calc(v, 505, 604, 401, 500);
    }
    
    if (pollutant === 'NO2') {
        // Assuming 'c' is in µg/m³; ~0.53 converts it to ppb
        let v = Math.floor(c * 0.53);
        if (v <= 53) return calc(v, 0, 53, 0, 50);
        if (v <= 100) return calc(v, 54, 100, 51, 100);
        if (v <= 360) return calc(v, 101, 360, 101, 150);
        if (v <= 649) return calc(v, 361, 649, 151, 200);
        if (v <= 1249) return calc(v, 650, 1249, 201, 300);
        // NEW: Split the 301-500 range
        if (v <= 1649) return calc(v, 1250, 1649, 301, 400);
        return calc(v, 1650, 2049, 401, 500);
    }
    
    return 0;
}

function getTrueMaxAqi(city) {
    if (!city) return 0;
    return Math.max(
        calculateTrueEPA_AQI(city.pm25, 'PM25'),
        calculateTrueEPA_AQI(city.pm10, 'PM10'),
        calculateTrueEPA_AQI(city.o3, 'O3'),
        calculateTrueEPA_AQI(city.no2, 'NO2')
    );
}

function getAqiPinPosition(aqi) {
    if (aqi <= 50) return (aqi / 50) * 16.66;
    if (aqi <= 100) return 16.66 + ((aqi - 51) / 49) * 16.66;
    if (aqi <= 150) return 33.32 + ((aqi - 101) / 49) * 16.66;
    if (aqi <= 200) return 49.98 + ((aqi - 151) / 49) * 16.66;
    if (aqi <= 300) return 66.64 + ((aqi - 201) / 99) * 16.66;
    if (aqi <= 500) return 83.30 + ((aqi - 301) / 199) * 16.66;
    return 100;
}

function getAqiColor(aqi) {
    if (aqi <= 50) return '#28a745';      
    if (aqi <= 100) return '#ffc107';     
    if (aqi <= 150) return '#fd7e14';     
    if (aqi <= 200) return '#dc3545';     
    if (aqi <= 300) return '#6f42c1';     
    return '#800000';                     
}

function updateProgressBar(id, value, limit) {
    let pct = (value / limit) * 100;
    let bar = document.getElementById(id);
    if (!bar) return;
    bar.style.width = Math.min(pct, 100) + '%';
    bar.style.backgroundColor = pct >= 100 ? '#dc3545' : (pct >= 50 ? '#ffc107' : '#28a745');
}

// =========================================================
// 2. APP STATE & INITIALIZATION
// =========================================================

let allCityData = [];
let globalSelectedCity = "Las Piñas";
let mapInstance = null;
let predictionChartInstance = null;
let summaryChartInstance = null;

let polygonLayer = null;
let heatLayer = null;
let isHeatmapActive = false;
let geoJsonInstance = null;
let rawGeoData = null; 
let ncrMaskLayer = null; 
let topLabelsLayer = null; 

document.addEventListener('DOMContentLoaded', () => {
    fetch('/api/live-data')
        .then(res => {
            if (!res.ok) throw new Error("Server response wasn't OK");
            return res.json();
        })
        .then(data => {
            allCityData = data;
            document.getElementById('app-loader').style.display = 'none'; 
            document.getElementById('dashboard-content').style.opacity = 1; 
            initMap();
            updateDashboard(globalSelectedCity); 
            updateLeaderboard();
        })
        .catch(err => {
            console.error("Failed to load initial data:", err);
            // Replace the spinner with an error message so the user isn't stuck
            document.getElementById('app-loader').innerHTML = `
                <div style="color: #dc3545; text-align: center;">
                    <h2>⚠️ Connection Error</h2>
                    <p>Unable to reach the live satellite feed. Please try refreshing.</p>
                </div>`;
        });
});

// =========================================================
// 3. MAP ENGINE
// =========================================================

function initMap() {

   const isMobile = window.innerWidth <= 768;
    mapInstance = L.map('pollution-map', {
        dragging: true,
        tap: true          
    }).setView([14.5995, 120.9842], 11);
    
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap'
    }).addTo(mapInstance);
    
    polygonLayer = L.layerGroup().addTo(mapInstance);

    // 1. Define the string cleaner once
    const cleanName = (name) => name ? name.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/city/g, "").replace(/\bof\b/g, "").trim() : "";

    // 2. Pre-compute a Hash Map (Dictionary) for O(1) lookups
    const cityDataDict = {};
    if (allCityData && allCityData.length > 0) {
        allCityData.forEach(city => {
            cityDataDict[cleanName(city.name)] = city;
        });
    }

    fetch('/static/ncr_boundaries.geojson')
        .then(response => response.json())
        .then(geojsonData => {
            rawGeoData = geojsonData;

            geoJsonInstance = L.geoJSON(geojsonData, {
                style: function (feature) {
                    // O(1) Instant Lookup
                    let geoName = cleanName(feature.properties.ADM3_EN);
                    let cityData = cityDataDict[geoName]; 
                    
                    let polygonColor = cityData ? getAqiColor(getTrueMaxAqi(cityData)) : '#cccccc';
                    return { fillColor: polygonColor, weight: 2, opacity: 1, color: 'white', fillOpacity: 0.65 };
                },
                onEachFeature: function (feature, layer) {
                    // O(1) Instant Lookup
                    let geoName = cleanName(feature.properties.ADM3_EN);
                    let cityData = cityDataDict[geoName];

                    if (cityData) {
                        let hoverAqi = getTrueMaxAqi(cityData);
                        layer.bindTooltip(`<b>${cityData.name}</b><br>AQI: ${hoverAqi}`);

                        layer.on('click', () => updateDashboard(cityData.name));
                        
                        // Hardware-accelerated hover effects
                        layer.on('mouseover', function (e) {
                            if (isHeatmapActive) e.target.setStyle({ weight: 2, color: '#ffffff', opacity: 1, fillOpacity: 0 });
                            else e.target.setStyle({ weight: 3, color: '#333', fillOpacity: 0.8 });
                            
                            if (!L.Browser.ie && !L.Browser.opera && !L.Browser.edge) e.target.bringToFront();
                        });
                        
                        layer.on('mouseout', function (e) {
                            if (isHeatmapActive) e.target.setStyle({ opacity: 0, fillOpacity: 0 });
                            else geoJsonInstance.resetStyle(e.target);
                        });
                    }
                }
            }).addTo(polygonLayer);
        });
}

function toggleHeatmap() {
    isHeatmapActive = !isHeatmapActive;
    if (isHeatmapActive) {
        if (geoJsonInstance) geoJsonInstance.eachLayer(layer => layer.setStyle({ opacity: 0, fillOpacity: 0 }));
        const heatPoints = allCityData.map(c => [c.lat, c.lon, getTrueMaxAqi(c)]);
        
        heatLayer = L.idwLayer(heatPoints, {
            opacity: 0.6, maxZoom: 14, cellSize: 8, exp: 3, max: 200, 
            gradient: { 0.2: '#28a745', 0.4: '#ffc107', 0.6: '#fd7e14', 0.8: '#dc3545', 1.0: '#6f42c1' }
        }).addTo(mapInstance);

        if (rawGeoData) {
            ncrMaskLayer = L.geoJSON(turf.mask(rawGeoData), {
                style: { fillColor: '#ffffff', fillOpacity: 0.65, color: '#495057', weight: 2, dashArray: '6, 6' },
                interactive: false        
            }).addTo(mapInstance);
        }

        topLabelsLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png', {
            pane: 'shadowPane', zIndex: 1000, interactive: false
        }).addTo(mapInstance);
        
    } else {
        if (heatLayer) mapInstance.removeLayer(heatLayer);
        if (ncrMaskLayer) mapInstance.removeLayer(ncrMaskLayer);
        if (topLabelsLayer) mapInstance.removeLayer(topLabelsLayer); 
        if (geoJsonInstance) geoJsonInstance.eachLayer(layer => geoJsonInstance.resetStyle(layer));
    }
}

// =========================================================
// 4. CORE DASHBOARD UPDATER
// =========================================================

function updateDashboard(cityName) {
    const city = allCityData.find(c => c.name === cityName);
    if (!city) return;
    
    globalSelectedCity = city.name; 

    // A. CALCULATE THE "WINNING" POLLUTANT
    let currentAqi = getTrueMaxAqi(city);
    let currentAqiColor = getAqiColor(currentAqi);

    document.getElementById('current-section').style.borderTopColor = currentAqiColor;

    // B. TEXT & AQI BOX UPDATES
    document.getElementById('dom-city-name').innerText = "Live Conditions: " + city.name;
    document.getElementById('dom-timestamp').innerText = city.timestamp;
    
    document.getElementById('dom-aqi-number').innerText = currentAqi;
    document.getElementById('dom-aqi-number').style.color = currentAqiColor;
    document.getElementById('dom-aqi-box').style.borderLeftColor = currentAqiColor;

    // C. MOVE THE GRADIENT PIN (Using Hybrid Positioning)
    let pinPosition = getAqiPinPosition(currentAqi);
    document.getElementById('dom-aqi-pin').style.left = `${Math.max(0, pinPosition)}%`;
    document.getElementById('dom-aqi-pin').style.backgroundColor = currentAqiColor;

    // D. DYNAMIC PRIMARY POLLUTANT LABEL
    let o3Score = calculateTrueEPA_AQI(city.o3, 'O3');
    let primaryPol = (currentAqi === o3Score) ? "O₃" : "PM2.5";
    document.getElementById('dom-primary-val').innerText = primaryPol;
    
    const badge = document.getElementById('dom-primary-badge');
    badge.style.color = currentAqiColor;
    badge.style.backgroundColor = currentAqiColor + '15'; 
    badge.style.border = `1px solid ${currentAqiColor}40`;

    // E. WEATHER STATS
    document.getElementById('dom-temp').innerText = city.temp;
    document.getElementById('dom-humidity').innerText = city.humidity;
    document.getElementById('dom-precip').innerText = city.precipitation;
    document.getElementById('dom-wind').innerText = city.wind_speed;
    document.getElementById('dom-wind-arrow').style.transform = `rotate(${city.wind_direction}deg)`;

    // F. POLLUTANT BREAKDOWN BARS
    document.getElementById('dom-pm25').innerText = city.pm25 + " µg/m³";
    document.getElementById('dom-pm10').innerText = city.pm10 + " µg/m³";
    document.getElementById('dom-no2').innerText = city.no2 + " µg/m³";
    document.getElementById('dom-o3').innerText = city.o3 + " µg/m³";

    updateProgressBar('bar-pm25', city.pm25, 25);
    updateProgressBar('bar-pm10', city.pm10, 50);
    updateProgressBar('bar-no2', city.no2, 25);
    updateProgressBar('bar-o3', city.o3, 100);

    if (currentBreakdownView === 'pie') {
    drawBreakdownChart(city);
    }

    // G. HEALTH RECOMMENDATIONS & DESCRIPTIONS
    document.getElementById('dom-health-status').innerText = city.health.status + ":";
    document.getElementById('dom-health-status').style.color = currentAqiColor;
    document.getElementById('dom-health-desc').innerText = city.health.desc;

    document.getElementById('rec-exercise').innerText = city.health.exercise;
    document.getElementById('rec-window').innerText = city.health.window;
    document.getElementById('rec-mask').innerText = city.health.mask;
    document.getElementById('rec-purifier').innerText = city.health.purifier;

    document.querySelectorAll('.dom-bg-color').forEach(el => el.style.backgroundColor = city.health.bg);

    if (currentAqi <= 100) {
        document.getElementById('row-mask').style.display = 'none';
        document.getElementById('row-purifier').style.display = 'none';
    } else {
        document.getElementById('row-mask').style.display = 'flex';
        document.getElementById('row-purifier').style.display = 'flex';
    }

    // H. WEATHER INSIGHTS
    let insightText = "Standard weather conditions. Pollution levels are driven by local traffic and emissions.";
    if (city.precipitation > 0) insightText = "Current rainfall is actively washing particulate matter (PM2.5/PM10) out of the atmosphere, improving air quality.";
    else if (city.wind_speed > 5) insightText = "Strong winds (" + city.wind_speed + " m/s) are helping to disperse airborne pollutants, preventing smog buildup.";
    else if (city.wind_speed < 1.5 && city.temp > 30) insightText = "Stagnant air and high heat are creating a 'dome' effect, trapping pollutants and increasing ground-level ozone (O3) risks.";
    else if (city.wind_speed < 1.5) insightText = "Low wind speeds are causing pollutants to stagnate and accumulate over the city.";
    
    document.getElementById('dom-weather-insight').innerText = insightText;

    // I. TRENDS & CHARTS
    const trendColor = city.trend === 'worsening' ? '#dc3545' : (city.trend === 'improving' ? '#28a745' : '#6c757d');
    document.getElementById('dom-trend-text').innerHTML = `<span style="color:${trendColor}">${city.trend_icon} ${city.trend.charAt(0).toUpperCase() + city.trend.slice(1)}</span>`;

    const namesToKeys = {'PM2.5': 'pm2_5', 'PM10': 'pm10', 'NO₂': 'no2', 'O₃': 'o3'};
    document.getElementById('hist-pol-select').value = namesToKeys[primaryPol] || 'pm2_5';
    
    updateHistoryUI();

    const predictTab = document.getElementById('predict-section');
    if (predictTab && predictTab.classList.contains('active')) fetchPrediction(city.name);
}

// =========================================================
// 5. LEADERBOARD ENGINE
// =========================================================

function updateLeaderboard() {
    if (!allCityData || allCityData.length === 0) return;

    const sorted = [...allCityData].sort((a, b) => getTrueMaxAqi(a) - getTrueMaxAqi(b));
    const cleanest = sorted.slice(0, 3);
    const polluted = [...sorted].reverse().slice(0, 3);

    const renderCard = (city, index, isClean) => {
        const score = getTrueMaxAqi(city); 
        const color = getAqiColor(score);
        const bg = isClean ? '#f8fdf9' : '#fffcfc';
        const badge = index === 0 ? '🥇' : (index === 1 ? '🥈' : '🥉');

        return `
            <div onclick="updateDashboard('${city.name}')" style="display: flex; justify-content: space-between; align-items: center; background: ${bg}; padding: 12px; border-radius: 10px; border: 1px solid ${color}40; cursor: pointer; transition: transform 0.2s;">
                <span style="font-weight: 700; color: #2c3e50;">${badge} ${city.name.replace(" City", "")}</span>
                <span style="font-size: 0.9em; font-weight: 800; background: ${color}; color: white; padding: 4px 10px; border-radius: 15px;">AQI ${score}</span>
            </div>
        `;
    };

    document.getElementById('top-clean').innerHTML = cleanest.map((c, i) => renderCard(c, i, true)).join('');
    document.getElementById('top-polluted').innerHTML = polluted.map((c, i) => renderCard(c, i, false)).join('');
}

// =========================================================
// 6. HISTORICAL CHARTS & TABS
// =========================================================

let breakdownChart = null;


function switchTab(tabId, btn) {
    document.querySelectorAll(".tab-content").forEach(tab => tab.classList.remove("active"));
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.getElementById(tabId).classList.add("active");
    btn.classList.add("active");
    if (tabId === 'predict-section') fetchPrediction(globalSelectedCity);
}

function updateHistoryUI() {

    const city = allCityData.find(c => c.name === globalSelectedCity);
    if (!city || !city.history) return;

    const polKey = document.getElementById('hist-pol-select').value;
    const w_val = city.history[polKey][0]; 
    const m_val = city.history[polKey][1]; 

    const elWeeklyAvg = document.getElementById('dom-weekly-avg');
    const elMonthlyAvg = document.getElementById('dom-monthly-avg');
    const elWeeklyInsight = document.getElementById('dom-weekly-insight');
    const elMonthlyInsight = document.getElementById('dom-monthly-insight');

    elWeeklyAvg.innerText = w_val + (w_val !== "--" ? " µg/m³" : "");
    elMonthlyAvg.innerText = m_val + (m_val !== "--" ? " µg/m³" : "");

    let w_avg = parseFloat(w_val);
    let m_avg = parseFloat(m_val);

    if (!isNaN(w_avg) && !isNaN(m_avg)) {
        let percentDiff = ((w_avg - m_avg) / m_avg) * 100;
        elWeeklyInsight.innerHTML = percentDiff > 15 
            ? `🔺 <strong>Trending Worse:</strong> This week is ${percentDiff.toFixed(0)}% more polluted than your monthly average.`
            : (percentDiff < -15 
                ? `✅ <strong>Improving:</strong> This week is ${Math.abs(percentDiff).toFixed(0)}% cleaner than your baseline.`
                : `➡️ <strong>Stable:</strong> Pollution is holding steady at your monthly baseline.`);

        const whoLimits = { 'pm2_5': 5.0, 'pm10': 15.0, 'no2': 10.0, 'o3': 60.0 };
        let limit = whoLimits[polKey];
        
        if (m_avg > (limit * 3)) elMonthlyInsight.innerHTML = `⚠️ <strong>Hazardous Baseline:</strong> Long-term exposure is <strong>${(m_avg/limit).toFixed(1)}x</strong> higher than WHO safety limits (${limit} µg/m³).`;
        else if (m_avg > limit) elMonthlyInsight.innerHTML = `⚠️ <strong>Elevated Baseline:</strong> Your 30-day average is above WHO guidelines. Persistent exposure may impact health.`;
        else elMonthlyInsight.innerHTML = `✅ <strong>Safe Baseline:</strong> Your long-term exposure is within the recommended WHO annual safety limit.`;
    } else {
        elWeeklyInsight.innerHTML = "<em>Collecting trend data...</em>";
        elMonthlyInsight.innerHTML = "<em>Analyzing long-term baseline...</em>";
    }

    drawHistoricalChart(city.history);
}

function drawHistoricalChart(historyData) {
    const canvas = document.getElementById('summaryChart');
    if (!canvas) return; // Safety check
    const ctx = canvas.getContext('2d');
    
    if (summaryChartInstance) summaryChartInstance.destroy();

    const safeParse = (val) => val === "--" ? 0 : parseFloat(val);

    summaryChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['PM2.5', 'PM10', 'NO₂', 'O₃'], 
            datasets: [
                {
                    label: '7-Day Average', 
                    backgroundColor: '#6f42c1', 
                    borderRadius: 4,
                    data: [
                        safeParse(historyData.pm2_5[0]), 
                        safeParse(historyData.pm10[0]), 
                        safeParse(historyData.no2[0]), 
                        safeParse(historyData.o3[0])
                    ]
                },
                {
                    label: '30-Day Average', 
                    backgroundColor: '#dee2e6', 
                    borderRadius: 4,
                    data: [
                        safeParse(historyData.pm2_5[1]), 
                        safeParse(historyData.pm10[1]), 
                        safeParse(historyData.no2[1]), 
                        safeParse(historyData.o3[1])
                    ]
                }
            ]
        },
        options: {
            responsive: true, 
            maintainAspectRatio: false,
            scales: {
                x: { 
                    
                    grid: { display: false } 
                },
                y: { 
                    beginAtZero: true, 
                    title: { display: true, text: "Concentration (µg/m³)" } 
                },
            },
            plugins: { 
                legend: { 
                    display: true,
                    position: 'bottom'
                }
            }
        }
    });
}

function drawBreakdownChart(city) {
    const canvas = document.getElementById('breakdownChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (breakdownChart) breakdownChart.destroy();

    const scores = [
        { 
            id: 'PM25', label: 'PM2.5', 
            val: calculateTrueEPA_AQI(city.pm25, 'PM25'), 
            col: '#6f42c1', 
            src: 'Jeepneys, Buses, & Industrial Smoke', 
            desc: 'Microscopic soot from diesel engines. Highly dangerous to heart and lung health.' 
        },
        { 
            id: 'PM10', label: 'PM10',  
            val: calculateTrueEPA_AQI(city.pm10, 'PM10'), 
            col: '#adb5bd', 
            src: 'Construction Dust & Road Debris', 
            desc: 'Larger dust particles often kicked up by wind or heavy infrastructure projects.' 
        },
        { 
            id: 'NO2',  label: 'NO₂',   
            val: calculateTrueEPA_AQI(city.no2, 'NO2'),   
            col: '#007bff', 
            src: 'Main Road Traffic & Gridlock', 
            desc: 'Nitrogen gas from fuel combustion. Strongest during morning and evening rush hours.' 
        },
        { 
            id: 'O3',   label: 'O₃',    
            val: calculateTrueEPA_AQI(city.o3, 'O3'),    
            col: '#fd7e14', 
            src: 'Sunlight Reacting with Urban Smog', 
            desc: 'Formed when heat and light hit traffic exhaust. Peaks during the hottest part of the day.' 
        }
    ];

    // 2. Find the winner
    const winner = [...scores].sort((a, b) => b.val - a.val)[0];
    
    document.getElementById('dom-pie-total').innerText = winner.val;
    document.getElementById('dom-analysis-title').innerText = `${winner.label} is the majority`;
    
    document.getElementById('dom-analysis-body').innerText = winner.desc; 
    document.getElementById('dom-analysis-source').innerText = `PRIMARY SOURCE: ${winner.src}`;
    
    document.getElementById('pollutant-analysis-panel').style.borderLeftColor = winner.col;

    // 4. Render the Chart
    breakdownChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: scores.map(s => s.label),
            datasets: [{
                data: scores.map(s => s.val),
                backgroundColor: scores.map(s => s.col),
                borderWidth: 2,
                borderColor: '#ffffff',
                hoverOffset: 15
            }]
        },
        options: {
            cutout: '70%',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: (i) => ` ${i.label}: AQI ${i.raw}` } }
            }
        }
    });
}

let currentBreakdownView = 'bars'; // Default state

function toggleBreakdown(viewType) {
    currentBreakdownView = viewType;

    // 1. Update Button Styles
    document.getElementById('btn-view-bars').style.background = viewType === 'bars' ? '#fff' : 'transparent';
    document.getElementById('btn-view-bars').style.boxShadow = viewType === 'bars' ? '0 2px 4px rgba(0,0,0,0.05)' : 'none';
    
    document.getElementById('btn-view-pie').style.background = viewType === 'pie' ? '#fff' : 'transparent';
    document.getElementById('btn-view-pie').style.boxShadow = viewType === 'pie' ? '0 2px 4px rgba(0,0,0,0.05)' : 'none';

    // 2. Hide/Show Containers
    document.getElementById('view-container-bars').style.display = viewType === 'bars' ? 'grid' : 'none';
    document.getElementById('view-container-pie').style.display = viewType === 'pie' ? 'block' : 'none';

    if (viewType === 'pie') {
        const city = allCityData.find(c => c.name === globalSelectedCity);
        if (city) drawBreakdownChart(city);
    }
}


// =========================================================
// 7. PREDICTION ENGINE
// =========================================================

function fetchPrediction(cityName) {
    const alertBanner = document.getElementById("predict-alert-banner");
    const loadingDiv = document.getElementById("loading");
    const resultsDiv = document.getElementById("prediction-results");
    const reasonDiv = document.getElementById("dom-predict-reason");

    loadingDiv.style.display = "block";
    resultsDiv.style.display = "none";

    fetch("/predict", {
        method: "POST", 
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ city: cityName }),
    })
    .then(res => {
        if (!res.ok) return res.json().then(err => { throw new Error(err.error || "Server Error") });
        return res.json();
    })
    .then(data => {
        loadingDiv.style.display = "none";
        resultsDiv.style.display = "block";

        console.log("Python sent this chart data:", data.chart_data);

        if (reasonDiv && data.reason) reasonDiv.innerHTML = `<strong>Primary Driver:</strong> ${data.reason}`;

        if (data.alert_msg) {
            alertBanner.style.display = "block";
            alertBanner.innerText = data.alert_msg;
            alertBanner.style.borderLeftColor = data.alert_color;
            alertBanner.style.backgroundColor = data.alert_color + "15"; 
            alertBanner.style.color = "#333";
        } else {
            alertBanner.style.display = "none";
        }

        document.getElementById("next-hour-val").innerHTML = `${data.prediction} <span style="font-size: 0.3em; color: #333;">µg/m³</span>`;

        const ctx = document.getElementById("predictionChart").getContext("2d");
        if (predictionChartInstance) predictionChartInstance.destroy();

        predictionChartInstance = new Chart(ctx, {
            type: "line",
            data: {
                labels: data.chart_data.labels,
                datasets: [
                    { 
                        label: "Predicted PM2.5", 
                        data: data.chart_data.pm25, 
                        borderColor: data.alert_color, 
                        backgroundColor: data.alert_color + '33',
                        fill: true, 
                        tension: 0.4,
                        borderWidth: 3,
                        pointRadius: 3,
                        order: 1 // Keeps the prediction line on top
                    },
                    { 
                        label: "Yesterday's Levels", 
                        data: data.chart_data.yesterday, 
                        borderColor: '#7d6c6c', // A sleek gray color
                        borderDash: [5, 5],     // Makes the line dashed
                        fill: false, 
                        tension: 0.4,
                        borderWidth: 2,
                        pointRadius: 3,         // Hides the dots to keep it clean
                        spanGaps: true,         // Connects the line even if an hour is missing
                        order: 2
                    },
                    { 
                        label: "This Day Last Year", 
                        data: data.chart_data.last_year, 
                        borderColor: '#17a2b8', 
                        borderDash: [2, 4],    
                        fill: false, 
                        tension: 0.4,
                        borderWidth: 2,
                        pointRadius: 3,
                        spanGaps: true,
                        order: 3
                    }
                ]
            },
            options: { 
                responsive: true, 
                maintainAspectRatio: false,
                plugins: { 
                    legend: { 
                        display: false,      
                        position: 'bottom'
                    }, 
                    tooltip: { mode: 'index', intersect: false } 
                },
                scales: {
                    y: { title: { display: true, text: 'PM2.5 (µg/m³)' }, beginAtZero: true },
                    x: { type: "time", time: { unit: "hour" }, grid: { display: false } }
                }
            }
        });
    })
    .catch(err => {
        loadingDiv.style.display = "none";
        
        console.error("Fetch Error:", err);
    });
}

function toggleDataset(datasetIndex, checkbox) {
    if (predictionChartInstance) {
        // Chart.js built-in method to show/hide datasets
        const isVisible = predictionChartInstance.isDatasetVisible(datasetIndex);
        
        if (checkbox.checked) {
            predictionChartInstance.show(datasetIndex);
        } else {
            predictionChartInstance.hide(datasetIndex);
        }
        predictionChartInstance.update();
    }
}
