const API_BASE = "/api/v1";

let globalDocuments = [];
let selectedDocument = null;
let activeFilter = "all";
let osintMap = null;
let mapMarkers = [];
let notifiedDocs = new Set();

document.addEventListener("DOMContentLoaded", () => {
    initEventListeners();
    initMap();
    requestNotificationPermission();

    loadEvidenceDocuments();
    loadUserPersonalSources();

    // Auto-refresh evidence feed every 15 seconds for continuous live view
    setInterval(async () => {
        await loadEvidenceDocuments();
        await loadUserPersonalSources();
    }, 15000);
});

function initMap() {
    // Center map roughly on the Middle East / Europe to start
    osintMap = L.map('osint-map').setView([25.0, 45.0], 2);
    
    // Using standard, 100% free OpenStreetMap tiles. 
    // We will apply a dark theme via CSS filter so no keys/domains are needed.
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(osintMap);
}

function requestNotificationPermission() {
    if ("Notification" in window) {
        if (Notification.permission !== "granted" && Notification.permission !== "denied") {
            Notification.requestPermission();
        }
    }
}

async function geocodeLocation(locationName) {
    if (!locationName || locationName === 'Global' || locationName.length < 3) return null;
    try {
        // Using Open-Meteo's robust, free Geocoding API (No API Key Required)
        const res = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(locationName)}&count=1&format=json`);
        const data = await res.json();
        if (data.results && data.results.length > 0) {
            return [parseFloat(data.results[0].latitude), parseFloat(data.results[0].longitude)];
        }
    } catch (e) {
        console.warn("Geocoding failed for", locationName);
    }
    return null;
}

const geocodeCache = {};

async function updateMapAndNotifications(docs) {
    if (!osintMap) return;

    // Clear existing markers
    mapMarkers.forEach(m => osintMap.removeLayer(m));
    mapMarkers = [];

    // Add legend (once only)
    if (!document.getElementById('map-legend')) {
        const legend = L.control({ position: 'bottomright' });
        legend.onAdd = () => {
            const div = L.DomUtil.create('div');
            div.id = 'map-legend';
            div.innerHTML = `
                <div style="background:#0e1524; border:1px solid #1f293d; border-radius:8px; padding:10px 14px; font-size:0.75rem; color:#e5e7eb; box-shadow:0 4px 12px rgba(0,0,0,0.5);">
                    <div style="font-weight:700; margin-bottom:8px; color:#93c5fd; letter-spacing:0.05em;">⚠ THREAT LEVEL</div>
                    <div style="display:flex; flex-direction:column; gap:6px;">
                        <div style="display:flex; align-items:center; gap:8px;"><span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:#ef4444; box-shadow:0 0 8px #ef4444;"></span> CRITICAL</div>
                        <div style="display:flex; align-items:center; gap:8px;"><span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:#f97316; box-shadow:0 0 8px #f97316;"></span> HIGH</div>
                        <div style="display:flex; align-items:center; gap:8px;"><span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:#eab308; box-shadow:0 0 8px #eab308;"></span> MEDIUM</div>
                        <div style="display:flex; align-items:center; gap:8px;"><span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:#22c55e; box-shadow:0 0 8px #22c55e;"></span> LOW</div>
                    </div>
                </div>`;
            return div;
        };
        legend.addTo(osintMap);
    }

    const colorMap = {
        CRITICAL: { dot: '#ef4444', glow: 'rgba(239,68,68,0.6)' },
        HIGH:     { dot: '#f97316', glow: 'rgba(249,115,22,0.6)' },
        MEDIUM:   { dot: '#eab308', glow: 'rgba(234,179,8,0.6)' },
        LOW:      { dot: '#22c55e', glow: 'rgba(34,197,94,0.4)' }
    };

    for (const doc of docs) {
        const pred = doc.prediction || {};
        const threat = pred.threat_level || "LOW";
        const locName = doc.location_name;

        // 1. Desktop Notification for CRITICAL/HIGH new documents
        if (!notifiedDocs.has(doc.id)) {
            notifiedDocs.add(doc.id);
            if ((threat === "CRITICAL" || threat === "HIGH") &&
                "Notification" in window && Notification.permission === "granted") {
                new Notification(`VYU ALERT — ${threat} Threat`, {
                    body: doc.title,
                    icon: "/favicon.ico"
                });
            }
        }

        // 2. Plot on Map
        if (locName && locName !== "Global" && locName !== "Direct Link") {
            let coords = geocodeCache[locName];
            if (!coords) {
                coords = await geocodeLocation(locName);
                if (coords) geocodeCache[locName] = coords;
            }
            if (coords) {
                const c = colorMap[threat] || colorMap.LOW;
                // Build a highly visible pulsing marker
                const markerHtml = `
                    <div style="position:relative; width:20px; height:20px;">
                        <div style="
                            position:absolute; top:50%; left:50%;
                            transform:translate(-50%,-50%);
                            width:14px; height:14px; border-radius:50%;
                            background:${c.dot};
                            border:2px solid white;
                            box-shadow:0 0 0 3px ${c.glow}, 0 0 12px ${c.dot};
                            animation:vyu-pulse 1.8s ease-in-out infinite;
                        "></div>
                    </div>`;
                const icon = L.divIcon({
                    html: markerHtml,
                    className: '',
                    iconSize: [20, 20],
                    iconAnchor: [10, 10],
                    popupAnchor: [0, -12]
                });

                const escalation = Math.round((pred.escalation_probability || 0.1) * 100);
                const popupHtml = `
                    <div style="font-family:sans-serif; min-width:220px;">
                        <div style="font-weight:700; font-size:0.85rem; margin-bottom:6px; line-height:1.3;">${escapeHtml(doc.title)}</div>
                        <div style="display:flex; gap:6px; align-items:center; margin-bottom:6px;">
                            <span style="background:${c.dot}22; color:${c.dot}; border:1px solid ${c.dot}55; padding:2px 8px; border-radius:4px; font-size:0.7rem; font-weight:700;">⚠ ${threat}</span>
                            <span style="font-size:0.7rem; color:#6b7280;">📡 ${escapeHtml(doc.feed_type || 'LIVE').toUpperCase()}</span>
                        </div>
                        <div style="font-size:0.72rem; color:#6b7280; margin-bottom:4px;">📍 ${escapeHtml(locName)}</div>
                        <div style="font-size:0.72rem; color:#9ca3af;">Escalation Risk: <strong style="color:${c.dot}">${escalation}%</strong></div>
                        ${doc.url ? `<a href="${doc.url}" target="_blank" style="font-size:0.72rem; color:#3b82f6; display:block; margin-top:6px;">🔗 View Source</a>` : ''}
                    </div>`;

                const marker = L.marker(coords, { icon }).addTo(osintMap);
                marker.bindPopup(popupHtml, { maxWidth: 280, className: 'vyu-popup' });
                mapMarkers.push(marker);
            }
        }
    }
}

function initEventListeners() {
    // Collection trigger
    document.getElementById("btn-collect").addEventListener("click", triggerCollection);

    // Personal Source / Topic Tracker
    document.getElementById("btn-add-personal").addEventListener("click", addPersonalTopic);
    document.getElementById("personal-topic-input").addEventListener("keypress", (e) => {
        if (e.key === "Enter") addPersonalTopic();
    });

    // Ask VYU Chatbot
    document.getElementById("btn-ask").addEventListener("click", submitAskQuery);
    const ragInput = document.getElementById("rag-input");
    ragInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitAskQuery(); }
    });
    ragInput.addEventListener("input", () => {
        ragInput.style.height = "auto";
        ragInput.style.height = Math.min(ragInput.scrollHeight, 150) + "px";
    });

    // Clear chat
    document.getElementById("btn-clear-chat").addEventListener("click", () => {
        const msgs = document.getElementById("chatbot-messages");
        msgs.innerHTML = `
            <div class="chat-msg ai">
                <div class="chat-ai-avatar"><i class="fa-solid fa-robot"></i></div>
                <div class="chat-bubble ai-bubble">
                    <p>Chat cleared. I'm ready for your next question!</p>
                    <p style="margin-top:6px; font-size:0.85rem; color:#9ca3af;">I'm continuously monitoring live global intelligence feeds.</p>
                </div>
            </div>`;
    });

    // Capture Modal controls
    const modal = document.getElementById("capture-modal");
    document.getElementById("btn-open-capture").addEventListener("click", () => modal.style.display = "flex");
    document.querySelector(".close-modal").addEventListener("click", () => modal.style.display = "none");
    document.getElementById("capture-form").addEventListener("submit", handleCaptureSubmit);

    // Filters
    document.querySelectorAll(".filter-item").forEach(item => {
        item.addEventListener("click", (e) => {
            document.querySelectorAll(".filter-item").forEach(i => i.classList.remove("active"));
            e.target.classList.add("active");
            activeFilter = e.target.dataset.filter;
            filterDocuments(activeFilter);
        });
    });
}

async function loadEvidenceDocuments() {
    try {
        const res = await fetch(`${API_BASE}/evidence`);
        const data = await res.json();
        globalDocuments = data.documents || [];
        filterDocuments(activeFilter);
        
        if (globalDocuments.length > 0 && !selectedDocument) {
            selectDocument(globalDocuments[0].id);
        }
        
        // Update Map and Notifications
        updateMapAndNotifications(globalDocuments);
    } catch (err) {
        console.error("Error loading live evidence documents:", err);
    }
}

async function loadUserPersonalSources() {
    try {
        const res = await fetch(`${API_BASE}/sources/user`);
        const data = await res.json();
        const sources = data.sources || [];
        const container = document.getElementById("personal-sources-list");
        if (sources.length === 0) {
            container.innerHTML = `<span style="color:var(--text-muted);">No personal trackers added yet. Add a city, topic, or RSS URL above.</span>`;
            return;
        }

        let html = `<strong style="color:var(--accent-color);"><i class="fa-solid fa-satellite-dish"></i> Live Personal Trackers (${sources.length}):</strong><div class="widget-grid">`;

        // Render each source as a rich widget
        sources.forEach(s => {
            // Find the latest document for this tracker from globalDocuments to show live data
            const recentDoc = globalDocuments.find(d => 
                (d.feed_type === 'personal_weather' || d.feed_type === 'personal_news' || d.feed_type === 'personal_rss') &&
                (d.location_name === s.name || d.location_name === s.url_or_query || (d.title && d.title.includes(s.name)))
            );

            if (recentDoc && recentDoc.feed_type === 'personal_weather') {
                // Parse weather text to build widget
                // Expected text format: "Temperature: 33C", "Condition: Partly Cloudy (WMO Code: 2)"
                const text = recentDoc.full_text || "";
                const tempMatch = text.match(/Temperature:\s*([\d\.]+)C/);
                const condMatch = text.match(/Condition:\s*([^\(]+)/);
                const temp = tempMatch ? tempMatch[1] : "--";
                const cond = condMatch ? condMatch[1].trim() : "Unknown";

                // Map condition to icon
                let icon = "fa-cloud";
                let condLower = cond.toLowerCase();
                if (condLower.includes("clear") || condLower.includes("sunny")) icon = "fa-sun";
                else if (condLower.includes("rain") || condLower.includes("drizzle")) icon = "fa-cloud-rain";
                else if (condLower.includes("thunder")) icon = "fa-cloud-bolt";
                else if (condLower.includes("snow")) icon = "fa-snowflake";
                else if (condLower.includes("partly")) icon = "fa-cloud-sun";

                // Forecast snippet from AI prediction if available
                let predMsg = "Live monitoring active";
                if (recentDoc.prediction && recentDoc.prediction.forecast_scenarios && recentDoc.prediction.forecast_scenarios.length > 0) {
                     predMsg = recentDoc.prediction.forecast_scenarios[0].scenario || predMsg;
                }

                html += `
                    <div class="tracker-widget" onclick="filterDocuments('personal_weather'); selectDocument('${recentDoc.id}')">
                        <button class="btn-del-widget" onclick="event.stopPropagation(); removePersonalTracker('${s.id}')"><i class="fa-solid fa-xmark"></i></button>
                        <div class="widget-header">
                            <span><i class="fa-solid fa-location-dot"></i> ${escapeHtml(s.name)}</span>
                            <i class="fa-solid fa-ellipsis"></i>
                        </div>
                        <div class="widget-main">
                            <i class="fa-solid ${icon} widget-icon"></i>
                            <div>
                                <span class="widget-temp">${temp}</span><span class="widget-unit">°C</span>
                            </div>
                            <div class="widget-info">
                                <strong>${cond}</strong><br>
                                <i class="fa-solid fa-robot" style="color:#00ff88;"></i> AI Active
                            </div>
                        </div>
                        <div class="widget-footer">
                            <i class="fa-solid fa-temperature-half"></i> ${predMsg.substring(0, 45)}...
                        </div>
                    </div>
                `;
            } else {
                // News or RSS Widget
                let title = recentDoc ? recentDoc.title.replace(`[PERSONAL TRACKER: ${s.name}]`, '').trim() : "Scanning for live updates...";
                html += `
                    <div class="tracker-widget widget-news" onclick="filterDocuments('personal_news'); if('${recentDoc ? recentDoc.id : ''}') selectDocument('${recentDoc ? recentDoc.id : ''}')">
                        <button class="btn-del-widget" onclick="event.stopPropagation(); removePersonalTracker('${s.id}')"><i class="fa-solid fa-xmark"></i></button>
                        <div class="widget-header">
                            <span><i class="fa-solid fa-newspaper"></i> ${escapeHtml(s.name)}</span>
                        </div>
                        <div class="widget-main" style="gap: 10px;">
                            <i class="fa-solid fa-tower-broadcast widget-icon"></i>
                            <div class="widget-info" style="font-size: 0.9rem;">
                                ${escapeHtml(title).substring(0, 60)}...
                            </div>
                        </div>
                        <div class="widget-footer">
                            Click for AI Risk Analysis
                        </div>
                    </div>
                `;
            }
        });

        html += `</div>`;
        container.innerHTML = html;
    } catch (err) {
        console.error("Error loading personal sources:", err);
    }
}

async function removePersonalTracker(sourceId) {
    try {
        await fetch(`${API_BASE}/sources/user/${sourceId}`, { method: "DELETE" });
        await loadUserPersonalSources();
        await loadEvidenceDocuments();
    } catch (err) {
        console.error("Failed to remove tracker:", err);
    }
}

async function addPersonalTopic() {
    const input = document.getElementById("personal-topic-input");
    const val = input.value.trim();
    if (!val) return;

    const btn = document.getElementById("btn-add-personal");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Collecting live data...`;

    try {
        const payload = {
            name: val,
            source_type: val.startsWith("http") ? "rss" : "topic",
            url_or_query: val
        };

        const res = await fetch(`${API_BASE}/sources/user`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const result = await res.json();

        input.value = "";
        await loadUserPersonalSources();
        await loadEvidenceDocuments();

        // Show notification
        const msg = result.message || "Tracker added!";
        const notif = document.createElement("div");
        notif.style.cssText = "position:fixed;top:70px;right:20px;background:#00ff88;color:#000;padding:10px 18px;border-radius:8px;font-weight:bold;z-index:9999;";
        notif.innerHTML = `<i class="fa-solid fa-check"></i> ${msg}`;
        document.body.appendChild(notif);
        setTimeout(() => notif.remove(), 4000);
        
        if (result.captured_documents && result.captured_documents.length > 0) {
            selectDocument(result.captured_documents[0].id);
        }
    } catch (err) {
        alert("Failed to add personal tracker: " + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-plus-circle"></i> Track My Personal Topic`;
    }
}

function renderDocumentsFeed(docs) {
    const feedContainer = document.getElementById("document-feed");
    const countBadge = document.getElementById("doc-count-badge");

    // Strict UI Deduplication by URL and Title
    const uniqueDocs = [];
    const seenKeys = new Set();
    for (const d of docs) {
        const key = (d.url || d.title || "").trim().toLowerCase();
        if (!seenKeys.has(key)) {
            seenKeys.add(key);
            uniqueDocs.push(d);
        }
    }

    countBadge.textContent = `${uniqueDocs.length} Unique Documents`;

    if (uniqueDocs.length === 0) {
        feedContainer.innerHTML = `<div class="placeholder-text"><p>No captured live documents found for this filter.</p></div>`;
        return;
    }

    feedContainer.innerHTML = uniqueDocs.map(doc => {
        const pred = doc.prediction || {};
        const threat = pred.threat_level || "LOW";
        const badgeClass = threat === "CRITICAL" || threat === "HIGH" ? "badge-danger" : (threat === "MEDIUM" ? "badge-warning" : "badge-success");
        const isSelected = selectedDocument && selectedDocument.id === doc.id;

        return `
            <div class="doc-card ${isSelected ? 'selected' : ''}" onclick="selectDocument('${doc.id}')">
                <div class="doc-meta">
                    <span><i class="fa-solid fa-satellite-dish"></i> ${doc.feed_type.toUpperCase()}</span>
                    <span>${doc.published_at ? doc.published_at.substring(0, 19).replace('T', ' ') : 'Live'}</span>
                </div>
                <div class="doc-title">${escapeHtml(doc.title)}</div>
                <div class="doc-snippet">${escapeHtml(doc.summary)}</div>
                <div class="prediction-badge-container">
                    <span class="badge ${badgeClass}">Threat: ${threat}</span>
                    <span class="badge">Escalation Index: ${(pred.escalation_probability * 100 || 15).toFixed(0)}%</span>
                </div>
            </div>
        `;
    }).join("");
}

function selectDocument(docId) {
    selectedDocument = globalDocuments.find(d => d.id === docId);
    filterDocuments(activeFilter);

    const detailContainer = document.getElementById("prediction-detail");
    if (!selectedDocument) return;

    const pred = selectedDocument.prediction || {};
    const threat = pred.threat_level || "LOW";
    const badgeClass = threat === "CRITICAL" || threat === "HIGH" ? "badge-danger" : (threat === "MEDIUM" ? "badge-warning" : "badge-success");
    const threatColor = threat === "CRITICAL" ? "#ef4444" : threat === "HIGH" ? "#f97316" : threat === "MEDIUM" ? "#f59e0b" : "#10b981";
    const scenarios = pred.forecast_scenarios || [];
    const entities = pred.entities_extracted || [];
    const escalation = ((pred.escalation_probability || 0.15) * 100).toFixed(0);

    detailContainer.innerHTML = `
        <div class="insp-header" style="margin-bottom: 20px; border-bottom: 1px solid var(--border-color); padding-bottom: 16px;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 12px;">
                <span class="badge ${badgeClass}" style="font-size: 0.8rem; padding: 4px 10px;">
                    <i class="fa-solid fa-triangle-exclamation"></i> Threat Level: ${threat}
                </span>
                <span style="font-size:0.8rem; color:var(--text-muted); background:rgba(255,255,255,0.05); padding:4px 8px; border-radius:4px;">
                    <i class="fa-solid fa-location-dot"></i> ${escapeHtml(selectedDocument.location_name || 'Global')}
                </span>
            </div>
            <h3 style="font-size:1.2rem; line-height:1.4; color:#f3f4f6; margin-bottom: 10px;">
                ${escapeHtml(selectedDocument.title)}
            </h3>
            <div style="font-size:0.8rem; color:var(--text-muted); display:flex; gap:16px;">
                <span><i class="fa-regular fa-clock"></i> ${selectedDocument.published_at ? selectedDocument.published_at.substring(0, 19).replace('T', ' ') : 'Live'}</span>
                <span><i class="fa-solid fa-link"></i> <a href="${selectedDocument.url}" target="_blank" style="color:var(--primary-color); text-decoration:none;">View Source</a></span>
            </div>
        </div>

        <div style="display:grid; grid-template-columns: 1fr; gap: 16px; margin-bottom: 20px;">
            <!-- AI Assessment Box -->
            <div style="background:linear-gradient(145deg, rgba(59,130,246,0.1), rgba(16,185,129,0.05)); border:1px solid rgba(59,130,246,0.2); border-radius:8px; padding:16px;">
                <h4 style="font-size:0.9rem; color:var(--primary-color); margin-bottom:10px; display:flex; align-items:center; gap:8px;">
                    <i class="fa-solid fa-wand-magic-sparkles"></i> AI Tactical Assessment
                </h4>
                <p style="font-size:0.9rem; line-height:1.5; color:#e5e7eb; margin-bottom:16px;">
                    ${escapeHtml(pred.predicted_impact || 'Baseline security monitoring clean. No immediate threat detected.')}
                </p>
                
                <div>
                    <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:6px; color:var(--text-muted);">
                        <span>Escalation Risk Probability</span>
                        <strong style="color:${threatColor}">${escalation}%</strong>
                    </div>
                    <div style="background-color:#1f293d; height:6px; border-radius:3px; overflow:hidden;">
                        <div style="width:${escalation}%; background-color:${threatColor}; height:100%; transition: width 0.5s;"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Scenarios & Entities Grid -->
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px;">
            <!-- Forecast Scenarios -->
            <div style="background:#0e1524; border:1px solid var(--border-color); border-radius:8px; padding:16px;">
                <h4 style="font-size:0.85rem; margin-bottom:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">
                    <i class="fa-solid fa-timeline"></i> Forecast Scenarios
                </h4>
                <div style="display:flex; flex-direction:column; gap:8px;">
                    ${scenarios.map((s, i) => `
                        <div style="font-size:0.8rem; background:rgba(0,0,0,0.2); padding:10px; border-radius:6px; border-left:3px solid ${i===0?'#ef4444':i===1?'#f59e0b':'#3b82f6'};">
                            <strong style="color:#e5e7eb; display:block; margin-bottom:4px;">${s.timeframe}</strong> 
                            <span style="color:#9ca3af; line-height:1.4;">${escapeHtml(s.scenario)}</span>
                        </div>
                    `).join("")}
                </div>
            </div>

            <!-- Extracted Entities -->
            <div style="background:#0e1524; border:1px solid var(--border-color); border-radius:8px; padding:16px;">
                <h4 style="font-size:0.85rem; margin-bottom:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">
                    <i class="fa-solid fa-tags"></i> Extracted Entities
                </h4>
                ${entities.length > 0 ? `
                    <div style="display:flex; flex-wrap:wrap; gap:8px;">
                        ${entities.map(e => `
                            <span style="font-size:0.75rem; background:rgba(59,130,246,0.1); border:1px solid rgba(59,130,246,0.2); color:#93c5fd; padding:4px 10px; border-radius:12px; display:inline-flex; align-items:center; gap:6px;">
                                <i class="fa-solid ${e.type==='LOCATION'?'fa-map-pin':e.type==='ORGANIZATION'?'fa-building':'fa-cube'}"></i> 
                                ${escapeHtml(e.name)}
                            </span>
                        `).join("")}
                    </div>
                ` : `<p style="font-size:0.8rem; color:var(--text-muted);">No prominent entities detected.</p>`}
            </div>
        </div>

        <!-- Captured Live Document Full Text -->
        <div>
            <h4 style="font-size:0.85rem; margin-bottom:10px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">
                <i class="fa-solid fa-file-lines"></i> Captured Raw Telemetry
            </h4>
            <div style="background-color:#080c14; border:1px solid var(--border-color); padding:16px; border-radius:8px; font-size:0.85rem; color:#a1a1aa; max-height:250px; overflow-y:auto; font-family:ui-monospace, monospace; line-height:1.6; white-space:pre-wrap;">${escapeHtml(selectedDocument.full_text)}</div>
        </div>
    `;
}

function fillAndSend(text) {
    document.getElementById("rag-input").value = text;
    submitAskQuery();
}

function scrollChatToBottom() {
    const el = document.getElementById("chatbot-messages");
    if (el) el.scrollTop = el.scrollHeight;
}

function appendUserMessage(query) {
    const msgs = document.getElementById("chatbot-messages");
    const el = document.createElement("div");
    el.className = "chat-msg user";
    el.innerHTML = `
        <div class="chat-bubble user-bubble">${escapeHtml(query)}</div>
        <div class="chat-user-avatar"><i class="fa-solid fa-user"></i></div>
    `;
    msgs.appendChild(el);
    scrollChatToBottom();
}

function appendTypingIndicator() {
    const msgs = document.getElementById("chatbot-messages");
    const el = document.createElement("div");
    el.className = "chat-msg ai";
    el.id = "typing-indicator";
    el.innerHTML = `
        <div class="chat-ai-avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="chat-bubble ai-bubble typing-bubble">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
    `;
    msgs.appendChild(el);
    scrollChatToBottom();
    return el;
}

function removeTypingIndicator() {
    const el = document.getElementById("typing-indicator");
    if (el) el.remove();
}

function appendAIResponse(data, query) {
    const msgs = document.getElementById("chatbot-messages");
    const summary = data.summary || data.answer || "No answer found.";
    const sources = data.sources || data.cited_sources || [];
    const count = data.searched_documents_count || sources.length;

    const threatColor = (t) => {
        if (t === "CRITICAL") return "#ef4444";
        if (t === "HIGH") return "#f97316";
        if (t === "MEDIUM") return "#f59e0b";
        return "#10b981";
    };

    const sourcesHtml = sources.length > 0 ? `
        <div class="chat-sources-section">
            <div class="chat-sources-label"><i class="fa-solid fa-file-shield"></i> Sources & Verified Proof (${sources.length})</div>
            ${sources.map(s => `
                <div class="chat-source-card">
                    <div class="chat-source-meta">
                        <span class="chat-threat-badge" style="background:${threatColor(s.threat_level)}22; color:${threatColor(s.threat_level)}; border:1px solid ${threatColor(s.threat_level)}55;">⚠ ${s.threat_level || 'LOW'}</span>
                        <span class="chat-source-tag">📡 ${s.feed_type || 'LIVE'}</span>
                        <span class="chat-source-tag">📍 ${escapeHtml(s.location || 'Global')}</span>
                    </div>
                    <a class="chat-source-link" href="${s.url || '#'}" target="_blank">${escapeHtml(s.title)}</a>
                    ${s.summary ? `<p class="chat-source-snippet">${escapeHtml(s.summary)}</p>` : ''}
                    <div class="chat-risk-bar-row">
                        <span>Escalation Risk</span>
                        <div class="chat-risk-bar"><div class="chat-risk-fill" style="width:${Math.round((s.escalation_probability||0.1)*100)}%; background:${threatColor(s.threat_level)};"></div></div>
                        <span>${Math.round((s.escalation_probability||0.1)*100)}%</span>
                    </div>
                </div>
            `).join('')}
        </div>
    ` : '';

    const summaryHtml = typeof marked !== "undefined" ? marked.parse(summary) : escapeHtml(summary);

    const el = document.createElement("div");
    el.className = "chat-msg ai";
    el.innerHTML = `
        <div class="chat-ai-avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="chat-bubble ai-bubble">
            <div class="chat-answer-text">${summaryHtml}</div>
            ${sourcesHtml}
            <div class="chat-msg-footer">
                <i class="fa-solid fa-circle-check" style="color:#10b981;"></i>
                ${count} documents analyzed · VYU RAG Engine v3.0
            </div>
        </div>
    `;
    msgs.appendChild(el);
    scrollChatToBottom();
}

async function submitAskQuery() {
    const inputEl = document.getElementById("rag-input");
    const query = inputEl.value.trim();
    if (!query) return;

    const btn = document.getElementById("btn-ask");
    btn.disabled = true;
    inputEl.disabled = true;
    inputEl.value = "";
    inputEl.style.height = "auto";

    appendUserMessage(query);
    appendTypingIndicator();

    try {
        const res = await fetch(`${API_BASE}/ask`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query })
        });
        const data = await res.json();
        removeTypingIndicator();
        appendAIResponse(data, query);
    } catch (err) {
        removeTypingIndicator();
        const msgs = document.getElementById("chatbot-messages");
        const el = document.createElement("div");
        el.className = "chat-msg ai";
        el.innerHTML = `
            <div class="chat-ai-avatar" style="background:#ef444422; color:#ef4444;"><i class="fa-solid fa-triangle-exclamation"></i></div>
            <div class="chat-bubble ai-bubble" style="border-color:#ef444433; color:#ef4444;">
                Connection error. Please ensure the VYU backend is running.
            </div>
        `;
        msgs.appendChild(el);
        scrollChatToBottom();
    } finally {
        btn.disabled = false;
        inputEl.disabled = false;
        inputEl.focus();
    }
}

async function handleCaptureSubmit(e) {
    e.preventDefault();
    const modal = document.getElementById("capture-modal");
    
    const payload = {
        title: document.getElementById("doc-title").value,
        feed_type: document.getElementById("doc-feed-type").value,
        location_name: document.getElementById("doc-location").value || "Global",
        url: document.getElementById("doc-url").value || null,
        full_text: document.getElementById("doc-text").value
    };

    try {
        const res = await fetch(`${API_BASE}/evidence/capture`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const result = await res.json();
        
        modal.style.display = "none";
        document.getElementById("capture-form").reset();
        
        await loadEvidenceDocuments();
        if (result.captured_document) {
            selectDocument(result.captured_document.id);
        }
    } catch (err) {
        alert("Failed to capture live document: " + err.message);
    }
}

async function triggerCollection() {
    const btn = document.getElementById("btn-collect");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Collecting Live...`;

    try {
        await fetch(`${API_BASE}/collect`, { method: "POST" });
        await loadEvidenceDocuments();
    } catch (err) {
        console.error("Collection error:", err);
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-arrows-rotate"></i> Trigger Instant Collection`;
    }
}

function filterDocuments(category) {
    if (category === "all") {
        renderDocumentsFeed(globalDocuments);
    } else {
        const filtered = globalDocuments.filter(d => d.feed_type === category);
        renderDocumentsFeed(filtered);
    }
}

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
