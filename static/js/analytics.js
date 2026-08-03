(function () {
  "use strict";

  /* ── colour helpers (theme-aware) ─────────────────── */
  function isDark() {
    return !document.body.classList.contains("light-mode");
  }

  function palette() {
    const d = isDark();
    return {
      grid: d ? "rgba(255,255,255,.07)" : "rgba(0,0,0,.08)",
      text: d ? "#9ca3af" : "#6b7280",
      line1: "#6366f1",
      line2: "#22d3ee",
      bar: "#818cf8",
      barAlt: "#f472b6",
      doughnut: ["#6366f1", "#22d3ee", "#f472b6", "#facc15", "#34d399"],
      heatLow: d ? "#1e1e2f" : "#e0e7ff",
      heatHigh: d ? "#818cf8" : "#4338ca",
    };
  }

  function chartDefaults() {
    const c = palette();
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: c.text, font: { size: 11 } } },
      },
      scales: {
        x: { ticks: { color: c.text, font: { size: 10 } }, grid: { color: c.grid } },
        y: { ticks: { color: c.text, font: { size: 10 } }, grid: { color: c.grid } },
      },
    };
  }

  let charts = [];

  function destroyAll() {
    charts.forEach((c) => { try { c?.destroy(); } catch (_) {} });
    charts = [];
  }

  function showChartError(containerId, message) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const parent = container.parentElement;
    if (parent) {
      while (parent.firstChild) parent.removeChild(parent.firstChild);
      const errDiv = document.createElement('div');
      errDiv.className = 'chart-error';
      errDiv.style.cssText = 'display:flex;align-items:center;justify-content:center;height:100%;color:#ef4444;font-size:13px;';
      errDiv.textContent = message || 'Chart failed to load';
      parent.appendChild(errDiv);
    }
  }

  function lineChart(id, labels, data, label, color) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    if (!labels || !data || labels.length === 0 || data.length === 0) {
      showChartError(id, 'No data available');
      return;
    }
    const cfg = chartDefaults();
    try {
      const ch = new Chart(ctx, {
        type: "line",
        data: {
          labels,
          datasets: [{
            label,
            data,
            borderColor: color || palette().line1,
            backgroundColor: (color || palette().line1) + "22",
            fill: true,
            tension: 0.35,
            pointRadius: 0,
          }],
        },
        options: cfg,
      });
      charts.push(ch);
    } catch (e) {
      console.error(`Failed to create line chart ${id}:`, e);
      showChartError(id, 'Chart rendering error');
    }
  }

  function barChart(id, labels, data, label, color) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    if (!labels || !data || labels.length === 0 || data.length === 0) {
      showChartError(id, 'No data available');
      return;
    }
    const cfg = chartDefaults();
    try {
      const ch = new Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [{
            label,
            data,
            backgroundColor: color || palette().bar,
            borderRadius: 4,
          }],
        },
        options: cfg,
      });
      charts.push(ch);
    } catch (e) {
      console.error(`Failed to create bar chart ${id}:`, e);
      showChartError(id, 'Chart rendering error');
    }
  }

  function horizontalBar(id, labels, data, label) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    if (!labels || !data || labels.length === 0 || data.length === 0) {
      showChartError(id, 'No data available');
      return;
    }
    const cfg = chartDefaults();
    cfg.indexAxis = "y";
    try {
      const ch = new Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [{
            label,
            data,
            backgroundColor: palette().doughnut.concat(palette().doughnut),
            borderRadius: 4,
          }],
        },
        options: cfg,
      });
      charts.push(ch);
    } catch (e) {
      console.error(`Failed to create horizontal bar chart ${id}:`, e);
      showChartError(id, 'Chart rendering error');
    }
  }

  function doughnutChart(id, labels, data) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    if (!labels || !data || labels.length === 0 || data.length === 0) {
      showChartError(id, 'No data available');
      return;
    }
    const c = palette();
    try {
      const ch = new Chart(ctx, {
        type: "doughnut",
        data: {
          labels,
          datasets: [{
            data,
            backgroundColor: c.doughnut,
            borderWidth: 0,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: "right", labels: { color: c.text, font: { size: 11 } } },
          },
        },
      });
      charts.push(ch);
    } catch (e) {
      console.error(`Failed to create doughnut chart ${id}:`, e);
      showChartError(id, 'Chart rendering error');
    }
  }

  function dualLineChart(id, labels, d1, d2, l1, l2) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    if (!labels || !d1 || !d2 || labels.length === 0 || d1.length === 0 || d2.length === 0) {
      showChartError(id, 'No data available');
      return;
    }
    const c = palette();
    const cfg = chartDefaults();
    try {
      const ch = new Chart(ctx, {
        type: "line",
        data: {
          labels,
          datasets: [
            { label: l1, data: d1, borderColor: c.line1, tension: 0.3, pointRadius: 2 },
            { label: l2, data: d2, borderColor: c.line2, tension: 0.3, pointRadius: 2 },
          ],
        },
        options: cfg,
      });
      charts.push(ch);
    } catch (e) {
      console.error(`Failed to create dual line chart ${id}:`, e);
      showChartError(id, 'Chart rendering error');
    }
  }

  function renderHeatmap(container, hm) {
    if (!container) return;
    container.innerHTML = "";
    if (!hm || !hm.matrix || !hm.hours || !hm.subjects) {
      container.innerHTML = '<div class="chart-error">Heatmap data unavailable</div>';
      return;
    }
    const c = palette();
    const maxVal = Math.max(...hm.matrix.flat(), 1);

    const header = document.createElement("div");
    header.className = "hm-row hm-header";
    const spacer = document.createElement("div");
    spacer.className = "hm-label";
    header.appendChild(spacer);
    hm.hours.forEach((h, i) => {
      if (i % 3 !== 0) {
        const empty = document.createElement("div");
        empty.className = "hm-cell";
        header.appendChild(empty);
        return;
      }
      const cell = document.createElement("div");
      cell.className = "hm-cell hm-hour";
      cell.textContent = h.replace(":00", "h");
      header.appendChild(cell);
    });
    container.appendChild(header);

    hm.subjects.forEach((subj, ri) => {
      const row = document.createElement("div");
      row.className = "hm-row";
      const lbl = document.createElement("div");
      lbl.className = "hm-label";
      lbl.textContent = subj;
      lbl.title = subj;
      row.appendChild(lbl);

      hm.matrix[ri].forEach((val) => {
        const cell = document.createElement("div");
        cell.className = "hm-cell";
        const t = val / maxVal;
        cell.style.background = interpolateColor(c.heatLow, c.heatHigh, t);
        cell.title = `${subj} — ${val} queries`;
        row.appendChild(cell);
      });
      container.appendChild(row);
    });
  }

  function interpolateColor(low, high, t) {
    const parse = (hex) => {
      hex = hex.replace("#", "");
      return [parseInt(hex.substring(0, 2), 16), parseInt(hex.substring(2, 4), 16), parseInt(hex.substring(4, 6), 16)];
    };
    const [r1, g1, b1] = parse(low);
    const [r2, g2, b2] = parse(high);
    const r = Math.round(r1 + (r2 - r1) * t);
    const g = Math.round(g1 + (g2 - g1) * t);
    const b = Math.round(b1 + (b2 - b1) * t);
    return `rgb(${r},${g},${b})`;
  }

  function renderKPIs(el, kpis) {
    if (!kpis) return;
    const items = [
      { label: "Total Queries", value: kpis.total_queries?.toLocaleString() || '0', icon: "📊" },
      { label: "Active Users", value: kpis.active_users?.toLocaleString() || '0', icon: "👥" },
      { label: "Avg Response", value: (kpis.avg_response_ms || '0') + " s", icon: "⚡" },
      { label: "Satisfaction", value: (kpis.satisfaction || '0') + " / 5", icon: "⭐" },
      { label: "Docs Indexed", value: kpis.documents_indexed || '0', icon: "📁" },
      { label: "Uptime", value: (kpis.uptime_pct || '0') + "%", icon: "🟢" },
    ];
    el.innerHTML = items.map(k => `
      <div class="kpi-card">
        <div class="kpi-card__icon">${k.icon}</div>
        <div class="kpi-card__label">${k.label}</div>
        <div class="kpi-card__value">${k.value}</div>
      </div>
    `).join("");
  }

  async function fetchData() {
    const rangeEl = document.getElementById("timeRange");
    const days = rangeEl ? rangeEl.value : "30";

    const res = await fetch(`/api/analytics?days=${days}`);
    if (!res.ok) throw new Error("Failed to fetch analytics data");
    return res.json();
  }

  async function render() {
    document.querySelectorAll('.chart-error, .global-error').forEach(el => el.remove());
    try {
      destroyAll();
      const d = await fetchData();
      console.log("Analytics data:", d);

      const kpiRow = document.getElementById("kpiRow");
      if (kpiRow) renderKPIs(kpiRow, d.kpis);

      // Chart.js is now guaranteed to be loaded (local script)
      lineChart("chartQueriesDay", d.queries_per_day?.labels, d.queries_per_day?.data, "Queries", palette().line1);
      doughnutChart("chartSatisfaction", d.satisfaction_dist?.labels, d.satisfaction_dist?.data);
      horizontalBar("chartTopDocs", d.top_documents?.map(x => x.name), d.top_documents?.map(x => x.count), "Queries");
      barChart("chartResponseTime", d.response_time_buckets?.labels, d.response_time_buckets?.data, "Requests", palette().barAlt);
      lineChart("chartUsersDay", d.users_per_day?.labels, d.users_per_day?.data, "Users", palette().line2);
      barChart("chartHourly", d.hourly_traffic?.labels, d.hourly_traffic?.data, "Requests", palette().bar);
      dualLineChart("chartWeekly", d.weekly_comparison?.labels, d.weekly_comparison?.this_week, d.weekly_comparison?.last_week, "This Week", "Last Week");

      const hmEl = document.getElementById("heatmapContainer");
      if (hmEl) renderHeatmap(hmEl, d.heatmap);
    } catch (err) {
      console.error("Render error:", err);
      const root = document.getElementById("analyticsRoot");
      if (root) {
        const errDiv = document.createElement('div');
        errDiv.className = 'global-error';
        errDiv.textContent = 'Failed to load analytics data.';
        root.prepend(errDiv);
      }
    }
  }

  function reload() { render(); }

  function init() {
    render();
    document.getElementById("refreshAnalytics")?.addEventListener("click", render);
    document.getElementById("timeRange")?.addEventListener("change", render);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();

  window._analyticsDashboard = { reload };
})();