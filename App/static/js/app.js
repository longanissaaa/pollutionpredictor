         let allCityData = [];
        let globalSelectedCity = "Parañaque City"; // Default city
        let mapInstance = null;
        let predictionChartInstance = null;

        // 1. Initialize Application
        document.addEventListener('DOMContentLoaded', () => {
            fetch('/api/live-data')
                .then(res => res.json())
                .then(data => {
                    allCityData = data;
                    document.getElementById('app-loader').style.display = 'none'; // Hide loader
                    document.getElementById('dashboard-content').style.opacity = 1; // Show dashboard
                    initMap();
                    updateDashboard(globalSelectedCity); 
                    updateLeaderboard();
                });
        });

        // 2. Build the Map
        let markerLayer = null;
        let heatLayer = null;
        let isHeatmapActive = false;

        // 2. Build the Map (UPDATED FOR HEATMAP)
        function initMap() {
            mapInstance = L.map('pollution-map').setView([14.5995, 120.9842], 11);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; OpenStreetMap'
            }).addTo(mapInstance);

            // Group all markers into one layer so we can hide them together
            markerLayer = L.layerGroup().addTo(mapInstance);
            
            

            allCityData.forEach(city => {
                const marker = L.circleMarker([city.lat, city.lon], {
                    radius: 12,
                    fillColor: city.health.color,
                    color: '#ffffff',
                    weight: 2,
                    fillOpacity: 0.9
                }).addTo(markerLayer); // <-- Notice we add to markerLayer now

                marker.bindTooltip(`<b>${city.name}</b><br>AQI: ${city.aqi}/5`);

                marker.on('click', () => {
                    updateDashboard(city.name);
                });
            });
            
        }

        // Heatmap Toggle
        function toggleHeatmap() {
            isHeatmapActive = !isHeatmapActive;

            if (isHeatmapActive) {
                // 1. THE CLICKABLE TRICK: Don't remove the markers, just make them invisible forcefields!
                markerLayer.eachLayer(layer => {
                    layer.setStyle({ opacity: 0, fillOpacity: 0 });
                });

                // 2. THE COLOR FIX: Use 'aqi' instead of 'pm25' to perfectly match the marker colors
                const heatPoints = allCityData.map(c => [
                    c.lat, 
                    c.lon, 
                    c.aqi // <-- We are using the 1 to 5 AQI score now
                ]);

                // 3. Render the cloud
                heatLayer = L.heatLayer(heatPoints, {
                    radius: 60,         // Large enough to bridge the gap between cities
                    blur: 50,           // High blur makes the dots melt together
                    minOpacity: 0.1,     // Prevents "hollow" centers and hard edges
                    maxZoom: 11,
                    max: 6,              // Set slightly higher than max AQI (5) for softer colors
                    gradient: {
                        0.1: '#28a745',  // Good
                        0.3: '#ffc107',  // Fair
                        0.5: '#fd7e14',  // Moderate
                        0.7: '#dc3545',  // Poor
                        1.0: '#6f42c1'   // Hazardous
                    }
                }).addTo(mapInstance);
                
            } else {
                // Turn OFF Heatmap
                if (heatLayer) mapInstance.removeLayer(heatLayer);
                
                markerLayer.eachLayer(layer => {
                    layer.setStyle({ opacity: 1, fillOpacity: 0.9 });
                });
            }
        }

        // 3. The Core UI Updater (Replaces Jinja)
        function updateDashboard(cityName) {
            const city = allCityData.find(c => c.name === cityName);
            if (!city) return;
            
            globalSelectedCity = city.name; // Save state for the Predict tab

            // Text Updates
            document.getElementById('dom-city-name').innerText = "Live Conditions: " + city.name;
            document.getElementById('dom-timestamp').innerText = city.timestamp;
            document.getElementById('dom-temp').innerText = city.temp;
            document.getElementById('dom-humidity').innerText = city.humidity;
            document.getElementById('dom-precip').innerText = city.precipitation;
            document.getElementById('dom-wind').innerText = city.wind_speed;
            document.getElementById('dom-wind-arrow').style.transform = `rotate(${city.wind_direction}deg)`;
            
            // Pollutants
            document.getElementById('dom-pm25').innerText = city.pm25 + " µg/m³";
            document.getElementById('dom-pm10').innerText = city.pm10 + " µg/m³";
            document.getElementById('dom-no2').innerText = city.no2 + " µg/m³";
            document.getElementById('dom-o3').innerText = city.o3 + " µg/m³";

            // AQI & Colors
            document.getElementById('dom-aqi-number').innerHTML = `${city.aqi}<span style="font-size: 0.35em; color: #adb5bd; margin-left: 2px;">/5</span>`;
            document.getElementById('dom-aqi-number').style.color = city.health.color;
            document.getElementById('dom-aqi-box').style.borderLeftColor = city.health.color;
            
            // Gradient Scale Pin
            document.getElementById('dom-aqi-pin').style.left = `${(city.aqi * 20) - 10}%`;
            document.getElementById('dom-aqi-pin').style.backgroundColor = city.health.color;

            // Health Description
            document.getElementById('dom-health-status').innerText = city.health.status + ":";
            document.getElementById('dom-health-status').style.color = city.health.color;
            document.getElementById('dom-health-desc').innerText = city.health.desc;

            // Trend & Primary
            const trendColor = city.trend === 'worsening' ? '#dc3545' : (city.trend === 'improving' ? '#28a745' : '#6c757d');
            document.getElementById('dom-trend-text').innerHTML = `<span style="color:${trendColor}">${city.trend_icon} ${city.trend.charAt(0).toUpperCase() + city.trend.slice(1)}</span>`;
            
            const badge = document.getElementById('dom-primary-badge');
            badge.style.color = city.health.color;
            badge.style.backgroundColor = city.health.bg;
            badge.style.border = `1px solid ${city.health.color}40`;
            document.getElementById('dom-primary-val').innerText = city.primary_pollutant;

            const namesToKeys = {'PM2.5': 'pm2_5', 'PM10': 'pm10', 'NO₂': 'no2', 'O₃': 'o3'};
            document.getElementById('hist-pol-select').value = namesToKeys[city.primary_pollutant] || 'pm2_5';
    
            // Trigger the UI update
            updateHistoryUI();
            // Draw Summary Chart
           drawHistoricalChart(city.history);
            // Health Recommendations Lists
            document.getElementById('rec-exercise').innerText = city.health.exercise;
            document.getElementById('rec-window').innerText = city.health.window;
            document.getElementById('rec-mask').innerText = city.health.mask;
            document.getElementById('rec-purifier').innerText = city.health.purifier;

            const predictTab = document.getElementById('predict-section');
            if (predictTab && predictTab.classList.contains('active')) {
       
            fetchPrediction(city.name);
            }
        

            const updateBar = (id, value, limit) => {
            let pct = (value / limit) * 100;
            let bar = document.getElementById(id);
            bar.style.width = Math.min(pct, 100) + '%';
            // Green if under 50%, Yellow if 50-100%, Red if over limit
            bar.style.backgroundColor = pct >= 100 ? '#dc3545' : (pct >= 50 ? '#ffc107' : '#28a745');
        };

            // Based on WHO/Standard thresholds 
            updateBar('bar-pm25', city.pm25, 25);
            updateBar('bar-pm10', city.pm10, 50);
            updateBar('bar-no2', city.no2, 25);
            updateBar('bar-o3', city.o3, 100);

            let insightText = "Standard weather conditions. Pollution levels are driven by local traffic and emissions.";

            if (city.precipitation > 0) {
                insightText = "Current rainfall is actively washing particulate matter (PM2.5/PM10) out of the atmosphere, improving air quality.";
            } else if (city.wind_speed > 5) {
                insightText = "Strong winds (" + city.wind_speed + " m/s) are helping to disperse airborne pollutants, preventing smog buildup.";
            } else if (city.wind_speed < 1.5 && city.temp > 30) {
                insightText = "Stagnant air and high heat are creating a 'dome' effect, trapping pollutants and increasing ground-level ozone (O3) risks.";
            } else if (city.wind_speed < 1.5) {
                insightText = "Low wind speeds are causing pollutants to stagnate and accumulate over the city.";
            }

            document.getElementById('dom-weather-insight').innerText = insightText;


            document.querySelectorAll('.dom-bg-color').forEach(el => {
                el.style.backgroundColor = city.health.bg;
            });
         // --- NEW: CONDITIONAL HIDING LOGIC ---
              // If AQI is 1 (Good) or 2 (Fair), hide the mask and purifier rows.
              if (city.aqi <= 2) {
                  document.getElementById('row-mask').style.display = 'none';
                  document.getElementById('row-purifier').style.display = 'none';
              } else {
                  // If AQI is 3, 4, or 5, show them!
                  document.getElementById('row-mask').style.display = 'flex';
                  document.getElementById('row-purifier').style.display = 'flex';
              }
        }

        let summaryChartInstance = null;

// 2. Create the function to draw the chart
    function drawHistoricalChart(historyData) {
    const ctx = document.getElementById('summaryChart').getContext('2d');
    
    // IMPORTANT: If a chart already exists, destroy it before drawing a new one.
    // This prevents the "canvas is already in use" glitch when switching cities.
    if (summaryChartInstance) {
        summaryChartInstance.destroy();
    }

    // Helper function: Convert missing data ("--") to 0 so the chart doesn't break
    const safeParse = (val) => val === "--" ? 0 : parseFloat(val);

    // 3. Configure and render the Chart.js instance
    summaryChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['PM2.5', 'PM10', 'NO₂', 'O₃'], // The pollutants
            datasets: [
                {
                    label: '7-Day Average',
                    backgroundColor: '#6f42c1', // Purple to match your HTML border
                    borderRadius: 4,            // Rounded corners on the bars
                    data: [
                        safeParse(historyData.pm2_5[0]),
                        safeParse(historyData.pm10[0]),
                        safeParse(historyData.no2[0]),
                        safeParse(historyData.o3[0])
                    ]
                },
                {
                    label: '30-Day Average',
                    backgroundColor: '#dee2e6', // Soft grey for the baseline
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
            maintainAspectRatio: false, // Allows it to stretch to your 250px div height
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Concentration (µg/m³)'
                    }
                }
            },
            plugins: {
                tooltip: {
                    mode: 'index',
                    intersect: false // Makes tooltips appear when hovering *near* the bars
                },
                legend: {
                    position: 'bottom' // Moves the legend out of the way
                }
            }
        }
    });
}

        // 4. Tab Switching Logic
        function switchTab(tabId, btn) {
           document.querySelectorAll(".tab-content").forEach(tab => tab.classList.remove("active"));
          document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    
          document.getElementById(tabId).classList.add("active");
          btn.classList.add("active");

        if (tabId === 'predict-section') {
        fetchPrediction(globalSelectedCity);
        }
    }
    function updateHistoryUI() {
    const city = allCityData.find(c => c.name === globalSelectedCity);
    if (!city || !city.history) return;

    const polKey = document.getElementById('hist-pol-select').value;
    const w_val = city.history[polKey][0]; // 7-Day Avg
    const m_val = city.history[polKey][1]; // 30-Day Avg

    const elWeeklyAvg = document.getElementById('dom-weekly-avg');
    const elMonthlyAvg = document.getElementById('dom-monthly-avg');
    const elWeeklyInsight = document.getElementById('dom-weekly-insight');
    const elMonthlyInsight = document.getElementById('dom-monthly-insight');

    // 1. Update Numeric Displays
    elWeeklyAvg.innerText = w_val + (w_val !== "--" ? " µg/m³" : "");
    elMonthlyAvg.innerText = m_val + (m_val !== "--" ? " µg/m³" : "");

    let w_avg = parseFloat(w_val);
    let m_avg = parseFloat(m_val);

    if (!isNaN(w_avg) && !isNaN(m_avg)) {
        // --- WEEKLY TREND LOGIC ---
        let percentDiff = ((w_avg - m_avg) / m_avg) * 100;
        elWeeklyInsight.innerHTML = percentDiff > 15 
            ? `🔺 <strong>Trending Worse:</strong> This week is ${percentDiff.toFixed(0)}% more polluted than your monthly average.`
            : (percentDiff < -15 
                ? `✅ <strong>Improving:</strong> This week is ${Math.abs(percentDiff).toFixed(0)}% cleaner than your baseline.`
                : `➡️ <strong>Stable:</strong> Pollution is holding steady at your monthly baseline.`);

        // --- MONTHLY BASELINE LOGIC (WHO Comparison) ---
        // WHO Annual Limits: PM2.5 (5), PM10 (15), NO2 (10), O3 (60)
        const whoLimits = { 'pm2_5': 5.0, 'pm10': 15.0, 'no2': 10.0, 'o3': 60.0 };
        let limit = whoLimits[polKey];
        
        if (m_avg > (limit * 3)) {
            elMonthlyInsight.innerHTML = `⚠️ <strong>Hazardous Baseline:</strong> Long-term exposure is <strong>${(m_avg/limit).toFixed(1)}x</strong> higher than WHO safety limits (${limit} µg/m³).`;
        } else if (m_avg > limit) {
            elMonthlyInsight.innerHTML = `⚠️ <strong>Elevated Baseline:</strong> Your 30-day average is above WHO guidelines. Persistent exposure may impact health.`;
        } else {
            elMonthlyInsight.innerHTML = `✅ <strong>Safe Baseline:</strong> Your long-term exposure is within the recommended WHO annual safety limit.`;
        }
    } else {
        elWeeklyInsight.innerHTML = "<em>Collecting trend data...</em>";
        elMonthlyInsight.innerHTML = "<em>Analyzing long-term baseline...</em>";
    }

    // Refresh the Chart
    drawHistoricalChart(city.history);
}

function drawHistoricalChart(historyData) {
    const ctx = document.getElementById('summaryChart').getContext('2d');
    if (summaryChartInstance) summaryChartInstance.destroy();

    const safeParse = (val) => val === "--" ? 0 : parseFloat(val);

    summaryChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['PM2.5', 'PM10', 'NO₂', 'O₃'],
            datasets: [
                {
                    label: '7-Day Avg',
                    backgroundColor: '#6f42c1',
                    borderRadius: 6,
                    data: [
                        safeParse(historyData.pm2_5[0]), safeParse(historyData.pm10[0]),
                        safeParse(historyData.no2[0]), safeParse(historyData.o3[0])
                    ]
                },
                {
                    label: '30-Day Baseline',
                    backgroundColor: '#e9ecef',
                    borderRadius: 6,
                    data: [
                        safeParse(historyData.pm2_5[1]), safeParse(historyData.pm10[1]),
                        safeParse(historyData.no2[1]), safeParse(historyData.o3[1])
                    ]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top', align: 'end' },
                tooltip: { mode: 'index', intersect: false }
            },
            scales: {
                y: { beginAtZero: true, grid: { drawBorder: false } },
                x: { grid: { display: false } }
            }
        }
    });
}
        // 5. Predict Logic (Unchanged except using globalSelectedCity)
    function fetchPrediction(cityName) {
    const alertBanner = document.getElementById("predict-alert-banner");
    const loadingDiv = document.getElementById("loading");
    const resultsDiv = document.getElementById("prediction-results");
    const reasonDiv = document.getElementById("dom-predict-reason");

    // 1. Show loading state
    loadingDiv.style.display = "block";
    resultsDiv.style.display = "none";

    fetch("/predict", {
        method: "POST", 
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ city: cityName }),
    })
    .then(res => {
        if (!res.ok) {
            return res.json().then(err => { throw new Error(err.error || "Server Error") });
        }
        return res.json();
    })
    .then(data => {
        // 2. Hide loading and show results
        loadingDiv.style.display = "none";
        resultsDiv.style.display = "block";

        // --- UPDATE EXPLAINABLE AI REASON (Moved inside the data scope) ---
        if (reasonDiv && data.reason) {
            reasonDiv.innerHTML = `<strong>Primary Driver:</strong> ${data.reason}`;
        }

        // --- ALERT BANNER ---
        if (data.alert_msg) {
            alertBanner.style.display = "block";
            alertBanner.innerText = data.alert_msg;
            alertBanner.style.borderLeftColor = data.alert_color;
            alertBanner.style.backgroundColor = data.alert_color + "15"; 
            alertBanner.style.color = "#333";
        } else {
            alertBanner.style.display = "none";
        }

        // --- UPDATE PM2.5 VALUE ---
        document.getElementById("next-hour-val").innerHTML = 
            `${data.prediction} <span style="font-size: 0.3em; color: #333;">µg/m³</span>`;

        // --- RENDER CHART ---
        const ctx = document.getElementById("predictionChart").getContext("2d");
        if (predictionChartInstance) predictionChartInstance.destroy();

        predictionChartInstance = new Chart(ctx, {
            type: "line",
            data: {
                labels: data.chart_data.labels,
                datasets: [{
                    label: "Predicted PM2.5", 
                    data: data.chart_data.pm25,
                    borderColor: "#28a745", 
                    backgroundColor: "rgba(40, 167, 69, 0.2)",
                    fill: true, 
                    tension: 0.4, 
                    borderWidth: 3, 
                    pointRadius: 3,
                }],
            },
            options: {
                responsive: true, 
                maintainAspectRatio: false,
                scales: {
                    x: { type: "time", time: { unit: "hour" }, grid: { display: false } },
                    y: { beginAtZero: true, title: { display: true, text: "PM2.5 (µg/m³)" } },
                },
                plugins: { legend: { display: false } },
            },
        });
    })
    .catch(err => {
        loadingDiv.style.display = "none";
        console.error("Fetch Error:", err);
    });
}

// Ensure Leaderboard updates based on current allCityData
// app.js: The Vertical Leaderboard Engine
function updateLeaderboard() {
    if (!allCityData || allCityData.length === 0) return;

    // 1. Sort by AQI (lowest to highest)
    const sorted = [...allCityData].sort((a, b) => a.aqi - b.aqi);

    // 2. Extract Top 3 for both ends
    const cleanest = sorted.slice(0, 3);
    const polluted = [...sorted].reverse().slice(0, 3);

    // 3. Render Cleanest (Vertical Stack)
    document.getElementById('top-clean').innerHTML = cleanest.map((city, index) => `
        <div style="display: flex; justify-content: space-between; align-items: center; background: #f8fdf9; padding: 8px 12px; border-radius: 6px; border: 1px solid #e1f5e8;">
            <span style="font-weight: 700; color: #28a745;">#${index + 1} ${city.name.replace(" City", "")}</span>
            <span style="font-size: 0.9em; background: #28a745; color: white; padding: 2px 8px; border-radius: 4px;">AQI ${city.aqi}</span>
        </div>
    `).join('');

    // 4. Render Polluted (Vertical Stack)
    document.getElementById('top-polluted').innerHTML = polluted.map((city, index) => `
        <div style="display: flex; justify-content: space-between; align-items: center; background: #fffcfc; padding: 8px 12px; border-radius: 6px; border: 1px solid #fbeaea;">
            <span style="font-weight: 700; color: #dc3545;">#${index + 1} ${city.name.replace(" City", "")}</span>
            <span style="font-size: 0.9em; background: #dc3545; color: white; padding: 2px 8px; border-radius: 4px;">AQI ${city.aqi}</span>
        </div>
    `).join('');
}