(function () {
  "use strict";

  const CONTRACT_VERSION = "main-analytics/v3";
  const charts = [];
  let requestNumber = 0;
  const number = (value) => Number(value).toLocaleString();
  const $ = (id) => document.getElementById(id);
  const message = (id, value) => { if ($(id)) $(id).textContent = value; };
  const theme = () => document.body.classList.contains("light-mode")
    ? { text: "#4b5563", grid: "rgba(0,0,0,.08)", low: "#e0e7ff", high: "#4338ca" }
    : { text: "#d1d5db", grid: "rgba(255,255,255,.08)", low: "#1e1e2f", high: "#818cf8" };

  function clearCharts() {
    charts.splice(0).forEach((chart) => chart.destroy());
    document.querySelectorAll(".chart-message").forEach((node) => node.remove());
    document.querySelectorAll(".chart-card canvas").forEach((canvas) => { canvas.hidden = false; });
  }

  function panelMessage(id, text, kind) {
    const canvas = $(id);
    if (!canvas) return;
    canvas.hidden = true;
    const node = document.createElement("p");
    node.className = `chart-message chart-message--${kind}`;
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    node.textContent = text;
    canvas.insertAdjacentElement("afterend", node);
  }

  function plot(id, type, labels, datasets, total, options = {}) {
    if (!total) return panelMessage(id, "No query activity in this period.", "empty");
    if (!window.Chart) {
      console.error("Analytics Chart.js unavailable for", id);
      return panelMessage(id, "Chart library unavailable.", "error");
    }
    const canvas = $(id);
    const colors = theme();
    const cfg = {
      responsive: true, maintainAspectRatio: false,
      indexAxis: options.horizontal ? "y" : "x",
      plugins: {
        legend: { display: datasets.length > 1 || type === "doughnut",
                  labels: { color: colors.text } },
        tooltip: { callbacks: { label(context) {
          const count = context.parsed?.y ?? context.parsed?.x ?? context.parsed;
          const label = type === "doughnut" ? context.label : context.dataset.label;
          return `${label}: ${number(count)}${options.denominator ? ` of ${number(options.denominator)}` : ""}`;
        } } },
      },
    };
    if (type !== "doughnut") cfg.scales = {
      x: { ticks: { color: colors.text }, grid: { color: colors.grid } },
      y: { beginAtZero: true, ticks: { color: colors.text, precision: 0 }, grid: { color: colors.grid } },
    };
    try {
      charts.push(new Chart(canvas, { type, data: { labels, datasets }, options: cfg }));
    } catch (error) {
      console.error("Analytics chart construction failed", id, error?.name || "Error", error?.message || "unknown error");
      panelMessage(id, "Chart could not be rendered. Reload this page or contact support.", "error");
    }
  }

  function series(label, data, color, type) {
    return { label, data, borderColor: color, backgroundColor: color,
             borderRadius: type === "bar" ? 4 : undefined,
             tension: type === "line" ? 0.25 : undefined,
             fill: false };
  }

  function renderKPIs(k) {
    const row = $("kpiRow");
    row.replaceChildren();
    const items = [
      ["Queries", number(k.total_queries), "Selected window"],
      ["Users who queried", number(k.active_users), "Distinct users in selected window"],
      ["Average completion", k.avg_completion_seconds === null ? "Unavailable" : `${k.avg_completion_seconds} s`,
       k.avg_completion_seconds === null ? "No completed queries with valid timestamps" : `${number(k.completion_measured)} of ${number(k.completed_queries)} completed queries measured`],
      ["Rated responses", number(k.rated_responses), `${number(k.total_queries)} queries in selected window`],
      ["Indexed documents", number(k.documents_indexed), "Global count at request time"],
    ];
    items.forEach(([label, value, detail]) => {
      const card = document.createElement("div");
      card.className = "kpi-card";
      for (const [cls, text] of [["kpi-card__label", label], ["kpi-card__value", value], ["kpi-card__detail", detail]]) {
        const part = document.createElement("div");
        part.className = cls;
        part.textContent = text;
        card.appendChild(part);
      }
      row.appendChild(card);
    });
  }

  function hexRgb(hex) { return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)); }
  function heatColor(value, maximum) {
    const colors = theme();
    const low = hexRgb(colors.low), high = hexRgb(colors.high), weight = value / maximum;
    return `rgb(${low.map((part, i) => Math.round(part + (high[i] - part) * weight)).join(",")})`;
  }

  function renderHeatmap(hm) {
    const root = $("heatmapContainer"), summary = $("heatmapSummary"), details = $("heatmapDetails");
    root.replaceChildren();
    summary.replaceChildren();
    details.hidden = !hm.total;
    message("heatmapMeta", `${number(hm.total)} queries · UTC weekday and hour`);
    if (!hm.total) {
      const empty = document.createElement("p");
      empty.className = "chart-message chart-message--empty";
      empty.textContent = "No query activity in this period.";
      root.appendChild(empty);
      return;
    }
    const maximum = Math.max(1, ...hm.matrix.flat());
    const header = document.createElement("div");
    header.className = "hm-row hm-header";
    const corner = document.createElement("span");
    corner.className = "hm-label";
    corner.textContent = "UTC";
    header.appendChild(corner);
    hm.hours.forEach((hour, index) => {
      const cell = document.createElement("span");
      cell.className = "hm-cell hm-hour";
      cell.textContent = index % 3 === 0 ? hour.slice(0, 2) : "";
      header.appendChild(cell);
    });
    root.appendChild(header);
    hm.weekdays.forEach((weekday, rowIndex) => {
      const row = document.createElement("div");
      row.className = "hm-row";
      const label = document.createElement("span");
      label.className = "hm-label";
      label.textContent = `${weekday} (${number(hm.weekday_totals[rowIndex])})`;
      row.appendChild(label);
      hm.matrix[rowIndex].forEach((count, hourIndex) => {
        const cell = document.createElement("span");
        cell.className = "hm-cell";
        cell.style.backgroundColor = heatColor(count, maximum);
        cell.title = `${weekday}, ${hm.hours[hourIndex]} UTC: ${number(count)} queries`;
        cell.setAttribute("aria-hidden", "true");
        row.appendChild(cell);
      });
      root.appendChild(row);
    });
    const table = document.createElement("table");
    table.className = "heatmap-table";
    const caption = document.createElement("caption");
    caption.textContent = `Query counts by weekday and hour in UTC; ${number(hm.total)} total`;
    table.appendChild(caption);
    const head = document.createElement("tr");
    ["Weekday", ...hm.hours, "Total"].forEach((value) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = value;
      head.appendChild(th);
    });
    table.appendChild(head);
    hm.weekdays.forEach((weekday, i) => {
      const row = document.createElement("tr"), th = document.createElement("th");
      th.scope = "row";
      th.textContent = weekday;
      row.appendChild(th);
      [...hm.matrix[i], hm.weekday_totals[i]].forEach((count) => {
        const td = document.createElement("td");
        td.textContent = number(count);
        row.appendChild(td);
      });
      table.appendChild(row);
    });
    summary.appendChild(table);
  }

  function renderData(d) {
    const k = d.kpis;
    message("analyticsTimezone", `${d.meta.days} UTC calendar days · ${d.meta.start} to ${d.meta.end} · Timezone: ${d.meta.timezone}`);
    renderKPIs(k);
    message("queriesDayMeta", `${number(k.total_queries)} queries · selected window`);
    plot("chartQueriesDay", "line", d.queries_per_day.labels,
         [series("Queries", d.queries_per_day.data, "#818cf8", "line")], k.total_queries);
    const feedback = d.feedback_outcomes;
    message("feedbackMeta", `${number(feedback.rated_responses)} rated responses / ${number(feedback.total_queries)} queries${feedback.other_values ? ` · ${number(feedback.other_values)} unrecognized vote values` : ""}`);
    plot("chartFeedback", "doughnut", feedback.labels,
         [series("Queries", feedback.data, ["#34d399", "#f472b6", "#818cf8"], "doughnut")], feedback.total_queries,
         { denominator: feedback.total_queries });
    const depth = d.conversation_depth;
    message("depthMeta", `${number(depth.sessions)} sessions · in-window queries only · ${number(depth.queries_without_session)} queries without session`);
    plot("chartDepth", "bar", depth.labels, [series("Sessions", depth.data, "#22d3ee", "bar")], depth.sessions,
         { denominator: depth.sessions });
    const duration = d.completion_duration;
    message("durationMeta", duration.measured
      ? `${number(duration.measured)} of ${number(duration.completed)} completed queries measured · ${number(duration.excluded_completed)} excluded`
      : `Unavailable: ${duration.unavailable_reason}`);
    if (duration.measured) plot("chartDuration", "bar", duration.labels,
      [series("Completed queries", duration.data, "#f472b6", "bar")], duration.measured,
      { denominator: duration.measured });
    else panelMessage("chartDuration", `Unavailable: ${duration.unavailable_reason}`, "unavailable");
    message("usersDayMeta", `${number(k.active_users)} distinct users in selected window; daily users may repeat across days`);
    plot("chartUsersDay", "line", d.users_per_day.labels,
         [series("Users", d.users_per_day.data, "#22d3ee", "line")], d.users_per_day.query_total);
    message("statesMeta", `${number(d.query_states.total)} queries · observed states only`);
    plot("chartStates", "bar", d.query_states.labels,
         [series("Queries", d.query_states.data, "#818cf8", "bar")], d.query_states.total,
         { denominator: d.query_states.total });
    const weekly = d.weekly_comparison;
    message("weeklyMeta", `Independent UTC 7-day windows · current ${number(weekly.current_total)} / previous ${number(weekly.previous_total)} queries`);
    plot("chartWeekly", "line", weekly.labels,
         [series("Current 7 days", weekly.current, "#818cf8", "line"),
          series("Previous 7 days", weekly.previous, "#22d3ee", "line")],
         weekly.current_total + weekly.previous_total);
    renderHeatmap(d.heatmap);
  }

  function showVersionMismatch(htmlVersion, apiVersion) {
    clearCharts();
    const root = $("analyticsRoot");
    root?.classList.add("contract-mismatch");
    let status = $("analyticsStatus");
    if (!status && root) {
      status = document.createElement("p");
      status.id = "analyticsStatus";
      status.className = "analytics-status";
      status.setAttribute("role", "alert");
      root.appendChild(status);
    }
    if (status) status.textContent =
      "Analytics version mismatch. Reload this page (Ctrl+Shift+R); if it persists, clear this site's cache or contact support.";
    console.error("Analytics contract mismatch", { html: htmlVersion, script: CONTRACT_VERSION, api: apiVersion });
  }

  async function render() {
    const thisRequest = ++requestNumber;
    const root = $("analyticsRoot");
    const htmlVersion = root?.dataset?.analyticsContract;
    if (htmlVersion !== CONTRACT_VERSION) {
      showVersionMismatch(htmlVersion, null);
      return;
    }
    root.classList.remove("contract-mismatch");
    clearCharts();
    $("kpiRow").replaceChildren();
    $("heatmapContainer").textContent = "Loading…";
    $("heatmapSummary").replaceChildren();
    $("heatmapDetails").hidden = true;
    message("analyticsTimezone", "");
    message("analyticsStatus", "Loading analytics…");
    for (const id of ["chartQueriesDay", "chartFeedback", "chartDepth", "chartDuration", "chartUsersDay", "chartStates", "chartWeekly"])
      panelMessage(id, "Loading…", "loading");
    try {
      const days = $("timeRange").value;
      const response = await fetch(`/api/analytics?days=${days}`, { credentials: "same-origin" });
      if (!response.ok) throw new Error("analytics request failed");
      const data = await response.json();
      if (thisRequest !== requestNumber) return;
      if (data.meta?.contract_version !== CONTRACT_VERSION) {
        showVersionMismatch(htmlVersion, data.meta?.contract_version);
        return;
      }
      clearCharts();
      renderData(data);
      message("analyticsStatus", `Analytics loaded for ${days} days in UTC.`);
    } catch (error) {
      if (thisRequest !== requestNumber) return;
      console.error("Analytics load/render failed", error?.name || "Error", error?.message || "unknown error");
      clearCharts();
      $("kpiRow").replaceChildren();
      message("analyticsTimezone", "");
      message("analyticsStatus", "Analytics could not be loaded. Refresh to retry.");
      for (const id of ["chartQueriesDay", "chartFeedback", "chartDepth", "chartDuration", "chartUsersDay", "chartStates", "chartWeekly"])
        panelMessage(id, "Data could not be loaded.", "error");
      $("heatmapContainer").textContent = "Data could not be loaded.";
      $("heatmapSummary").replaceChildren();
      $("heatmapDetails").hidden = true;
    }
  }

  function init() {
    render();
    $("refreshAnalytics")?.addEventListener("click", render);
    $("timeRange")?.addEventListener("change", render);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
  window._analyticsDashboard = { reload: render, contractVersion: CONTRACT_VERSION };
})();
