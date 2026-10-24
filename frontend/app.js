/**
 * VehicleGPT Frontend Application Logic
 * Manages API communication, real-time metrics, interactive charts, and natural-language query UI.
 */

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const queryForm = document.getElementById("query-form");
    const queryInput = document.getElementById("query-input");
    const btnSubmit = document.getElementById("btn-submit-query");
    const btnText = document.getElementById("btn-text");
    const btnSpinner = document.getElementById("btn-spinner");
    const toggleSlm = document.getElementById("toggle-slm");
    const exampleChips = document.querySelectorAll(".example-chips .chip");

    const answerText = document.getElementById("answer-text");
    const responseEngineBadge = document.getElementById("response-engine-badge");
    const retrievalTimeEl = document.getElementById("retrieval-time");
    const analyticsTimeEl = document.getElementById("analytics-time");
    const totalTimeEl = document.getElementById("total-time");
    const evidenceTableBody = document.getElementById("evidence-table-body");
    const evidenceCountEl = document.getElementById("evidence-count");

    const cardSoc = document.getElementById("card-soc");
    const cardRange = document.getElementById("card-range");
    const cardTemp = document.getElementById("card-temp");
    const cardEfficiency = document.getElementById("card-efficiency");
    const cardWarnings = document.getElementById("card-warnings");
    const cardAdas = document.getElementById("card-adas");

    const timelineList = document.getElementById("timeline-list");
    const btnResetDemo = document.getElementById("btn-reset-demo");
    const footerDbStatus = document.getElementById("footer-db-status");
    const aiStatusText = document.getElementById("ai-status-text");
    const aiStatusDot = document.getElementById("ai-status-dot");

    let chartInstance = null;
    let activeChartSignal = "battery_temperature";

    // =========================================================================
    // Initialization & Data Loading
    // =========================================================================
    async function initDashboard() {
        await checkSystemHealth();
        await loadVehicleSummary();
        await loadEventTimeline();
        await renderTelemetryChart(activeChartSignal);
    }

    // Health check
    async function checkSystemHealth() {
        try {
            const res = await fetch("/api/health");
            if (res.ok) {
                const data = await res.json();
                footerDbStatus.textContent = `SQLite: ${data.database.telemetry_records} telemetry, ${data.database.event_records} events`;

                if (data.ai_engine.ollama_available) {
                    aiStatusDot.className = "status-dot green";
                    aiStatusText.textContent = `SLM: Local (${data.ai_engine.configured_model})`;
                } else {
                    aiStatusDot.className = "status-dot blue";
                    aiStatusText.textContent = "SLM: Deterministic Engine";
                }
            }
        } catch (err) {
            console.warn("Health check error:", err);
            footerDbStatus.textContent = "DB: Connection Error";
        }
    }

    // Load top summary cards
    async function loadVehicleSummary() {
        try {
            const res = await fetch("/api/vehicle/summary");
            if (res.ok) {
                const data = await res.json();
                cardSoc.textContent = data.battery_soc_pct.toFixed(1);
                cardRange.textContent = Math.round(data.driving_range_km);
                cardTemp.textContent = data.battery_temp_c.toFixed(1);
                cardEfficiency.textContent = data.energy_consumption_kwh.toFixed(1);
                cardWarnings.textContent = data.critical_warnings_count;
                cardAdas.textContent = data.adas_disengagements_24h;

                if (data.critical_warnings_count > 0) {
                    cardWarnings.parentElement.style.color = "var(--status-critical)";
                }
            }
        } catch (err) {
            console.error("Failed to load vehicle summary:", err);
        }
    }

    // Load event timeline
    async function loadEventTimeline() {
        try {
            const res = await fetch("/api/events?limit=25");
            if (res.ok) {
                const data = await res.json();
                timelineList.innerHTML = "";
                if (!data.events || data.events.length === 0) {
                    timelineList.innerHTML = '<div class="empty-table-msg">No recent vehicle events logged.</div>';
                    return;
                }

                data.events.forEach(e => {
                    const item = document.createElement("div");
                    const sev = (e.severity || "INFO").toLowerCase();
                    item.className = `timeline-item ${sev}`;

                    const dateObj = new Date(e.timestamp);
                    const timeStr = isNaN(dateObj) ? e.timestamp : dateObj.toUTCString().replace("GMT", "UTC");

                    item.innerHTML = `
                        <div class="timeline-item-header">
                            <span class="timeline-type">${escapeHtml(e.event_type)}</span>
                            <span class="timeline-timestamp">${escapeHtml(timeStr)}</span>
                        </div>
                        <div class="timeline-desc">${escapeHtml(e.description)}</div>
                    `;
                    timelineList.appendChild(item);
                });
            }
        } catch (err) {
            console.error("Failed to load events:", err);
            timelineList.innerHTML = '<div class="empty-table-msg">Unable to load event stream.</div>';
        }
    }

    // =========================================================================
    // Natural-Language Query Handler
    // =========================================================================
    queryForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const question = queryInput.value.trim();
        if (!question) return;

        await submitQuery(question);
    });

    // Chip click handlers
    exampleChips.forEach(chip => {
        chip.addEventListener("click", () => {
            const q = chip.getAttribute("data-query");
            queryInput.value = q;
            submitQuery(q);
        });
    });

    async function submitQuery(question) {
        setQueryLoading(true);

        try {
            const payload = {
                question: question,
                use_llm: toggleSlm.checked,
            };

            const response = await fetch("/api/query", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || "Query execution failed.");
            }

            const data = await response.json();
            renderQueryResponse(data);
        } catch (error) {
            answerText.textContent = `Error executing query: ${error.message}`;
            responseEngineBadge.textContent = "Error";
            responseEngineBadge.style.color = "var(--status-critical)";
        } finally {
            setQueryLoading(false);
        }
    }

    function setQueryLoading(isLoading) {
        if (isLoading) {
            btnSubmit.disabled = true;
            btnText.textContent = "Analyzing...";
            btnSpinner.classList.remove("hidden");
            answerText.textContent = "Retrieving vehicle telemetry, event logs, and calculating deterministic analytics...";
            evidenceTableBody.innerHTML = '<tr><td colspan="7" class="empty-table-msg">Searching and validating historical evidence...</td></tr>';
        } else {
            btnSubmit.disabled = false;
            btnText.textContent = "Query Vehicle";
            btnSpinner.classList.add("hidden");
        }
    }

    function renderQueryResponse(data) {
        // Render answer text
        answerText.textContent = data.answer;

        // Engine badge
        responseEngineBadge.textContent = `Engine: ${data.model_used}`;
        if (data.model_used.includes("local-slm")) {
            responseEngineBadge.style.color = "var(--accent-teal-light)";
            responseEngineBadge.style.borderColor = "var(--accent-teal)";
        } else {
            responseEngineBadge.style.color = "var(--accent-cyan)";
        }

        // Latencies
        retrievalTimeEl.textContent = `${data.latency.retrieval_ms} ms`;
        analyticsTimeEl.textContent = `${data.latency.analytics_ms} ms`;
        totalTimeEl.textContent = `${data.latency.total_ms} ms`;

        // Render Evidence Table
        renderEvidenceTable(data.evidence);
    }

    function renderEvidenceTable(evidence) {
        evidenceTableBody.innerHTML = "";
        const count = evidence ? evidence.length : 0;
        evidenceCountEl.textContent = `${count} Records`;

        if (!evidence || evidence.length === 0) {
            evidenceTableBody.innerHTML = '<tr><td colspan="7" class="empty-table-msg">No specific record evidence returned for this query.</td></tr>';
            return;
        }

        evidence.forEach(item => {
            const tr = document.createElement("tr");

            const valStr = item.value !== null && item.value !== undefined ? item.value : "--";
            const unitStr = item.unit || "--";
            const sev = (item.severity || "INFO").toUpperCase();

            let sevBadgeClass = "badge-info";
            if (sev === "CRITICAL") sevBadgeClass = "badge-critical";
            else if (sev === "WARNING") sevBadgeClass = "badge-warning";

            tr.innerHTML = `
                <td><code>${escapeHtml(item.timestamp)}</code></td>
                <td><span class="badge ${sevBadgeClass}">${escapeHtml(item.record_type)}</span></td>
                <td><strong>${escapeHtml(item.label)}</strong></td>
                <td>${escapeHtml(String(valStr))}</td>
                <td>${escapeHtml(unitStr)}</td>
                <td><span class="badge ${sevBadgeClass}">${escapeHtml(sev)}</span></td>
                <td>${escapeHtml(item.details || "--")} <small style="color:var(--text-muted)">(${escapeHtml(item.source || "SYSTEM")})</small></td>
            `;
            evidenceTableBody.appendChild(tr);
        });
    }

    // =========================================================================
    // Historical Telemetry Charts (Chart.js)
    // =========================================================================
    const chartButtons = document.querySelectorAll(".chart-btn");
    chartButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            chartButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            activeChartSignal = btn.getAttribute("data-signal");
            renderTelemetryChart(activeChartSignal);
        });
    });

    async function renderTelemetryChart(signalName) {
        const canvas = document.getElementById("telemetryChart");
        if (!canvas) return;

        try {
            const res = await fetch(`/api/trends?signal_name=${encodeURIComponent(signalName)}&limit=300`);
            if (!res.ok) return;

            const data = await res.json();
            const series = data.series || [];

            // Downsample if more than 100 points for crisp visual performance
            const step = Math.max(1, Math.floor(series.length / 80));
            const sampled = series.filter((_, idx) => idx % step === 0);

            const labels = sampled.map(r => {
                const d = new Date(r.timestamp);
                return isNaN(d) ? r.timestamp.slice(5, 16) : `${d.getUTCMonth()+1}/${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}`;
            });
            const values = sampled.map(r => r.value);
            const unit = series.length > 0 ? series[0].unit : "";

            if (chartInstance) {
                chartInstance.destroy();
            }

            // Check if Chart.js is loaded
            if (typeof Chart === "undefined") {
                canvas.parentElement.innerHTML = `<div class="empty-table-msg">Chart visualization rendered without external CDN: ${signalName} (Latest: ${values[values.length - 1]} ${unit})</div>`;
                return;
            }

            const ctx = canvas.getContext("2d");
            chartInstance = new Chart(ctx, {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [{
                        label: `${signalName.replace(/_/g, ' ').toUpperCase()} (${unit})`,
                        data: values,
                        borderColor: signalName === "battery_temperature" ? "#F59E0B" : (signalName === "energy_consumption" ? "#EF4444" : "#14B8A6"),
                        backgroundColor: "rgba(20, 184, 166, 0.08)",
                        borderWidth: 2,
                        tension: 0.25,
                        fill: true,
                        pointRadius: 2,
                        pointHoverRadius: 5,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            grid: { color: "rgba(35, 51, 77, 0.4)" },
                            ticks: { color: "#94A3B8", maxTicksLimit: 10, font: { size: 10 } }
                        },
                        y: {
                            grid: { color: "rgba(35, 51, 77, 0.4)" },
                            ticks: { color: "#94A3B8", font: { size: 10 } }
                        }
                    },
                    plugins: {
                        legend: {
                            labels: { color: "#F8FAFC", font: { size: 12, weight: 600 } }
                        },
                        tooltip: {
                            backgroundColor: "#162032",
                            borderColor: "#23334D",
                            borderWidth: 1,
                            titleColor: "#F8FAFC",
                            bodyColor: "#14B8A6",
                        }
                    }
                }
            });
        } catch (err) {
            console.error("Failed to render chart:", err);
        }
    }

    // =========================================================================
    // Reset Demo Dataset
    // =========================================================================
    btnResetDemo.addEventListener("click", async () => {
        if (!confirm("Reset database and regenerate the 3-week synthetic vehicle dataset?")) {
            return;
        }

        btnResetDemo.disabled = true;
        btnResetDemo.textContent = "Resetting...";

        try {
            const res = await fetch("/api/demo/reset", { method: "POST" });
            if (res.ok) {
                alert("Demo dataset successfully reset and re-seeded!");
                await initDashboard();
            } else {
                const data = await res.json();
                alert(`Reset failed: ${data.detail || "Server error"}`);
            }
        } catch (err) {
            alert(`Error resetting database: ${err.message}`);
        } finally {
            btnResetDemo.disabled = false;
            btnResetDemo.textContent = "↺ Reset Demo Dataset";
        }
    });

    // Helper: Safe HTML escape
    function escapeHtml(str) {
        if (str === null || str === undefined) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Initialize on load
    initDashboard();
});
