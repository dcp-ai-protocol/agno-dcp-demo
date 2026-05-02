// agno-dcp-demo · client-side controller.
// Handles SSE subscription to the audit chain, scenario execution,
// chain verification, and Compliance Bundle exports.

(() => {
  const $ = (sel) => document.querySelector(sel);
  const log = $("#audit-log");
  const emptyState = $("#audit-empty-state");
  const kpiEntries = $("#kpi-entries");
  const kpiIntegrity = $("#kpi-integrity");
  const sseStatus = $("#sse-status");
  let entryCount = 0;

  const EVENT_STYLES = {
    AGENT_CREATED:    { color: "brand", label: "AGENT CREATED",    icon: "👤" },
    INTENT_DECLARED:  { color: "sky",   label: "INTENT",           icon: "→"  },
    POLICY_DECISION:  { color: "amber", label: "POLICY",           icon: "⚖"  },
    TOOL_EXECUTED:    { color: "emerald", label: "TOOL EXECUTED",  icon: "▸"  },
    TEAM_MESSAGE:     { color: "purple", label: "TEAM MESSAGE",    icon: "↔"  },
    MCP_INBOUND:      { color: "fuchsia", label: "MCP IN",         icon: "←"  },
    MCP_OUTBOUND:     { color: "fuchsia", label: "MCP OUT",        icon: "→"  },
    WORKFLOW_STEP:    { color: "indigo", label: "WORKFLOW",        icon: "≡"  },
    ERROR:            { color: "rose",  label: "ERROR",            icon: "!" },
  };

  const colorClasses = {
    brand:    "bg-brand-500/10 text-brand-300 border-brand-500/30",
    sky:      "bg-sky-500/10 text-sky-300 border-sky-500/30",
    amber:    "bg-amber-500/10 text-amber-300 border-amber-500/30",
    emerald:  "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
    purple:   "bg-purple-500/10 text-purple-300 border-purple-500/30",
    fuchsia:  "bg-fuchsia-500/10 text-fuchsia-300 border-fuchsia-500/30",
    indigo:   "bg-indigo-500/10 text-indigo-300 border-indigo-500/30",
    rose:     "bg-rose-500/10 text-rose-300 border-rose-500/30",
  };

  function shortHash(h) {
    if (!h) return "";
    if (h === "GENESIS") return "GENESIS";
    return h.slice(0, 8) + "…" + h.slice(-6);
  }

  function fmtTime(ts) {
    if (!ts) return "";
    try {
      return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch { return ts; }
  }

  function summarizePayload(eventType, payload) {
    if (!payload) return null;
    if (eventType === "POLICY_DECISION") {
      const ok = payload.approved;
      const reason = payload.reason || "";
      const rule = payload.rule_name || "(default)";
      return { primary: ok ? "ALLOW" : "DENY",
               primaryClass: ok ? "text-emerald-400" : "text-rose-400",
               secondary: `${rule} · ${reason}` };
    }
    if (eventType === "INTENT_DECLARED") {
      const ap = payload.action_payload || {};
      const tool = ap.tool_name || payload.action_type;
      return { primary: tool, primaryClass: "text-sky-300",
               secondary: Object.keys(ap).filter(k => k !== "tool_name").map(k => `${k}=${JSON.stringify(ap[k])}`).join(" · ") };
    }
    if (eventType === "TOOL_EXECUTED") {
      const tool = payload.tool_name || "(unknown)";
      const ok = payload.ok !== false;
      return { primary: tool, primaryClass: ok ? "text-emerald-300" : "text-rose-300",
               secondary: payload.result_summary || (ok ? "ok" : "failed") };
    }
    if (eventType === "AGENT_CREATED") {
      return { primary: payload.agent_name || "agent", primaryClass: "text-brand-300",
               secondary: `tier ${payload.security_tier} · principal ${payload.human_principal}` };
    }
    if (eventType === "ERROR") {
      return { primary: payload.error_type || "Error", primaryClass: "text-rose-400",
               secondary: payload.error_message || payload.reason || "" };
    }
    return null;
  }

  function appendEntry(entry, opts = {}) {
    if (emptyState && emptyState.parentElement) emptyState.remove();
    const meta = EVENT_STYLES[entry.event_type] || { color: "slate", label: entry.event_type, icon: "·" };
    const colorCls = colorClasses[meta.color] || "bg-slate-700/30 text-slate-300 border-slate-600";
    const summary = summarizePayload(entry.event_type, entry.payload);

    const card = document.createElement("div");
    card.className = "border border-slate-800 rounded-lg bg-slate-950/40 px-3 py-2.5" + (opts.highlight ? " audit-entry-new" : "");
    card.innerHTML = `
      <div class="flex items-start gap-3">
        <div class="flex-shrink-0 flex flex-col items-center">
          <span class="font-mono text-[10px] text-slate-500">#${entry.entry_index}</span>
          <span class="mt-0.5 font-mono text-[10px] text-slate-600">${fmtTime(entry.created_at)}</span>
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold border ${colorCls}">
              ${meta.label}
            </span>
            ${summary ? `<span class="text-xs font-semibold ${summary.primaryClass}">${summary.primary}</span>` : ""}
          </div>
          ${summary && summary.secondary ? `<div class="mt-1 text-[11px] text-slate-400">${summary.secondary}</div>` : ""}
          <div class="mt-1.5 flex items-center gap-3 text-[10px] font-mono text-slate-500">
            <span>prev: ${shortHash(entry.prev_hash)}</span>
            <span>this: ${shortHash(entry.entry_hash)}</span>
          </div>
        </div>
      </div>
    `;
    log.appendChild(card);
    // keep scroll at bottom on each new entry
    log.scrollTop = log.scrollHeight;

    entryCount += 1;
    kpiEntries.textContent = entryCount;
  }

  // ─── SSE wiring ──────────────────────────────────────────────
  function connectSSE() {
    const es = new EventSource("/api/audit/stream");
    es.addEventListener("hello", () => {
      sseStatus.classList.remove("bg-rose-500/10", "text-rose-400", "border-rose-500/20");
      sseStatus.classList.add("bg-emerald-500/10", "text-emerald-400", "border-emerald-500/20");
      sseStatus.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>live';
    });
    es.addEventListener("audit", (e) => {
      try {
        const entry = JSON.parse(e.data);
        appendEntry(entry, { highlight: true });
      } catch (err) { console.error("audit parse", err); }
    });
    es.onerror = () => {
      sseStatus.classList.remove("bg-emerald-500/10", "text-emerald-400", "border-emerald-500/20");
      sseStatus.classList.add("bg-rose-500/10", "text-rose-400", "border-rose-500/20");
      sseStatus.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>reconnecting';
    };
    return es;
  }

  // ─── Initial state ──────────────────────────────────────────
  async function loadInitialEntries() {
    const r = await fetch("/api/audit/entries?limit=500");
    const data = await r.json();
    log.innerHTML = "";
    if (!data.entries || data.entries.length === 0) {
      log.innerHTML = '<div class="text-center py-12 text-slate-500 text-sm">Audit log is empty. Run a scenario to see live entries.</div>';
      kpiEntries.textContent = 0;
      entryCount = 0;
      return;
    }
    entryCount = 0;
    for (const e of data.entries) appendEntry(e);
  }

  // ─── Public actions wired from buttons ──────────────────────
  window.runScenario = async (scenario) => {
    await fetch("/api/agent/scenario", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario }),
    });
    // SSE will pick up the new entries; nothing else to do.
  };

  window.verifyChain = async () => {
    const result = $("#verify-result");
    result.innerHTML = '<div class="text-slate-400">Verifying...</div>';
    const r = await fetch("/api/audit/verify");
    const data = await r.json();
    const intact = data.chain_intact;
    kpiIntegrity.textContent = intact ? "OK" : "FAIL";
    kpiIntegrity.classList.toggle("text-emerald-400", intact);
    kpiIntegrity.classList.toggle("text-rose-400", !intact);
    result.innerHTML = `
      <div class="border ${intact ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-rose-500/30 bg-rose-500/5'} rounded-md p-3">
        <div class="font-semibold ${intact ? 'text-emerald-400' : 'text-rose-400'}">
          ${intact ? '✓ Chain integrity verified' : '✗ Chain integrity failed'}
        </div>
        <div class="mt-1 text-slate-400 text-[11px] font-mono">
          entries_checked=${data.entries_checked} · roots_checked=${data.roots_checked} · roots_invalid=${data.roots_invalid.length}
        </div>
      </div>
    `;
  };

  window.exportBundle = async (framework) => {
    const result = $("#bundle-result");
    result.innerHTML = '<div class="text-slate-400">Generating signed bundle...</div>';
    const r = await fetch(`/api/audit/export?framework=${framework}`, { method: "POST" });
    const data = await r.json();
    const sizeKb = (data.size_bytes / 1024).toFixed(1);
    result.innerHTML = `
      <div class="border border-brand-500/30 bg-brand-500/5 rounded-md p-3">
        <div class="font-semibold text-brand-300">Compliance Bundle ready</div>
        <div class="mt-1 text-slate-400 text-[11px] font-mono">${data.framework} · ${data.filename} · ${sizeKb} KB</div>
        <a href="${data.download_url}" download class="mt-2 inline-flex items-center gap-1.5 text-brand-400 hover:text-brand-300 text-xs font-medium">
          ↓ Download signed ZIP
        </a>
      </div>
    `;
  };

  window.resetDemo = async () => {
    if (!confirm("Reset the audit chain back to genesis? This wipes all events from the demo run.")) return;
    await fetch("/api/audit/reset", { method: "POST" });
    await loadInitialEntries();
  };

  window.refreshAudit = loadInitialEntries;

  // ─── Boot ────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", async () => {
    await loadInitialEntries();
    connectSSE();
    // Trigger an initial integrity check so the KPI shows OK.
    setTimeout(() => window.verifyChain(), 800);
  });
})();
