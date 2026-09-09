/* ==============================================================================
   Maigret OSINT Investigation Platform - Client Logic
   ============================================================================== */

let ws = null;
let currentEngineMeta = { sites_count: 4990, sites_count_formatted: "4,990", version: "0.6.5" };
let guiActiveJobId = null;
const terminalHistory = [];
let historyIndex = -1;

// ------------------------------------------------------------------------------
// Utilities
// ------------------------------------------------------------------------------
function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
    
    const targetTab = document.getElementById(tabId);
    if (targetTab) targetTab.classList.add('active');

    const targetBtn = Array.from(document.querySelectorAll('.nav-btn')).find(b => {
        const oc = b.getAttribute('onclick') || '';
        return oc.includes(tabId);
    });
    if (targetBtn) targetBtn.classList.add('active');

    if (tabId === 'terminal') {
        const input = document.getElementById('term-input');
        if (input) input.focus();
    }
}

function openModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.style.display = 'flex';
}

function closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.style.display = 'none';
}

// ------------------------------------------------------------------------------
// Command Builder & Live Preview
// ------------------------------------------------------------------------------
function buildCommandTokens() {
    const user = (document.getElementById('gui-username-input')?.value || '').trim();
    if (!user) return ["maigret"];

    const tokens = ["maigret", user];

    // Target Range
    if (document.getElementById('opt-allsites')?.checked) {
        tokens.push("-a");
    } else if (document.getElementById('opt-use-top')?.checked) {
        const topVal = parseInt(document.getElementById('opt-top')?.value || '500');
        if (!isNaN(topVal) && topVal > 0) {
            tokens.push("--top-sites", topVal.toString());
        }
    }

    if (document.getElementById('opt-use-idtype')?.checked) {
        const idType = document.getElementById('opt-idtype')?.value;
        if (idType && idType !== "username") {
            tokens.push("--id-type", idType);
        }
    }

    // Filters & Modifiers
    if (document.getElementById('opt-permute')?.checked) {
        tokens.push("--permute");
    }
    if (document.getElementById('opt-cf-bypass')?.checked) {
        tokens.push("--cloudflare-bypass");
    }
    if (document.getElementById('opt-no-recursion')?.checked) {
        tokens.push("--no-recursion");
    }
    if (document.getElementById('opt-no-progressbar')?.checked) {
        tokens.push("--no-progressbar");
    }
    if (document.getElementById('opt-use-timeout')?.checked) {
        const tVal = parseInt(document.getElementById('opt-timeout')?.value || '15');
        if (!isNaN(tVal) && tVal > 0) {
            tokens.push("--timeout", tVal.toString());
        }
    }
    if (document.getElementById('opt-use-tags')?.checked) {
        const tagsStr = (document.getElementById('opt-tags')?.value || '').trim();
        if (tagsStr) {
            tokens.push("--tags", tagsStr);
        }
    }

    // Reports
    if (document.getElementById('rep-html')?.checked) {
        tokens.push("--html");
    }
    if (document.getElementById('rep-pdf')?.checked) {
        tokens.push("--pdf");
    }
    if (document.getElementById('rep-json')?.checked) {
        tokens.push("--json", "simple");
    }
    if (document.getElementById('rep-csv')?.checked) {
        tokens.push("--csv");
    }
    if (document.getElementById('rep-txt')?.checked) {
        tokens.push("--txt");
    }
    if (document.getElementById('rep-md')?.checked) {
        tokens.push("--md");
    }
    if (document.getElementById('rep-graph')?.checked) {
        tokens.push("--graph");
    }
    if (document.getElementById('rep-xmind')?.checked) {
        tokens.push("--xmind");
    }

    return tokens;
}

function updateCommandPreview() {
    const previewEl = document.getElementById('cmd-preview-display');
    if (!previewEl) return;

    const tokens = buildCommandTokens();
    if (tokens.length === 1 && tokens[0] === "maigret") {
        previewEl.innerHTML = '<span class="cmd-prog">maigret</span> <span style="color: #718096;">&lt;username&gt;</span>';
        return;
    }

    let html = `<span class="cmd-prog">${tokens[0]}</span> <span class="cmd-arg">${escapeHtml(tokens[1])}</span>`;
    for (let i = 2; i < tokens.length; i++) {
        const t = tokens[i];
        if (t.startsWith("-")) {
            html += ` <span class="cmd-flag">${escapeHtml(t)}</span>`;
        } else {
            html += ` <span class="cmd-arg">${escapeHtml(t)}</span>`;
        }
    }
    previewEl.innerHTML = html;
}

function toggleTopSitesOption() {
    const useTop = document.getElementById('opt-use-top')?.checked;
    const topInput = document.getElementById('opt-top');
    if (topInput) topInput.disabled = !useTop;
    if (useTop && document.getElementById('opt-allsites')?.checked) {
        document.getElementById('opt-allsites').checked = false;
    }
    updateCommandPreview();
}

function toggleAllSitesOption() {
    const isAll = document.getElementById('opt-allsites')?.checked;
    if (isAll && document.getElementById('opt-use-top')?.checked) {
        document.getElementById('opt-use-top').checked = false;
        const topInput = document.getElementById('opt-top');
        if (topInput) topInput.disabled = true;
    }
    updateCommandPreview();
}

function toggleIdTypeOption() {
    const useId = document.getElementById('opt-use-idtype')?.checked;
    const sel = document.getElementById('opt-idtype');
    if (sel) sel.disabled = !useId;
    updateCommandPreview();
}

function toggleTimeoutOption() {
    const useT = document.getElementById('opt-use-timeout')?.checked;
    const input = document.getElementById('opt-timeout');
    if (input) input.disabled = !useT;
    updateCommandPreview();
}

function toggleTagsOption() {
    const useTags = document.getElementById('opt-use-tags')?.checked;
    const input = document.getElementById('opt-tags');
    if (input) input.disabled = !useTags;
    updateCommandPreview();
}

function togglePdfOptions() {
    const isChecked = document.getElementById('rep-pdf')?.checked;
    const container = document.getElementById('pdf-options-container');
    if (container) container.style.display = isChecked ? 'block' : 'none';
    updateCommandPreview();
}

// ------------------------------------------------------------------------------
// Unsynced Terminal Output Handlers
// ------------------------------------------------------------------------------
function appendGuiLine(line) {
    const output = document.getElementById('gui-live-output');
    if (!output) return;

    const div = document.createElement('div');
    if (line.includes("FOUND") || ((line.includes("[+]") || line.includes("[++]") || line.includes("[?]")) && line.includes("http") && !line.includes("MAIGRET") && !line.includes("Using sites"))) {
        div.style.color = "var(--accent-gold)";
        div.style.fontWeight = "bold";
    } else if (line.startsWith("[!]")) {
        div.style.color = "var(--status-red)";
    } else if (line.startsWith("$ maigret") || line.startsWith("[*] Engine Executing")) {
        div.style.color = "#38bdf8";
        div.style.fontWeight = "bold";
    } else if (line.startsWith("[-]")) {
        div.style.color = "#94a3b8";
    }

    div.textContent = line;
    output.appendChild(div);
    output.scrollTop = output.scrollHeight;
}

function appendTerminalLine(text) {
    const term = document.getElementById('term-output');
    if (!term) return;
    term.innerHTML += escapeHtml(text) + "\n";
    term.scrollTop = term.scrollHeight;
}

function clearGuiOutput() {
    const output = document.getElementById('gui-live-output');
    if (output) output.innerHTML = '<span style="color: var(--text-dim);">Live terminal output cleared.</span>';
}

function clearTerminal() {
    const term = document.getElementById('term-output');
    if (term) term.innerHTML = "Console cleared.\n";
}

// ------------------------------------------------------------------------------
// WebSocket Routing
// ------------------------------------------------------------------------------
function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/terminal`);

    ws.onmessage = function (event) {
        try {
            const data = JSON.parse(event.data);
            if (data.type === "terminal_log") {
                const source = data.source || (data.job_id ? "gui" : "terminal");
                
                // UN-SYNCED: Route exclusively to the originating window
                if (source === "terminal") {
                    appendTerminalLine(data.line);
                } else if (source === "gui") {
                    if (!guiActiveJobId || data.job_id === guiActiveJobId) {
                        appendGuiLine(data.line);
                    }
                }
            } else if (data.type === "job_status") {
                if (data.job && data.job.id === guiActiveJobId) {
                    const dot = document.getElementById('gui-status-dot');
                    if (dot) {
                        if (data.job.status === "running") dot.classList.add('active');
                        else dot.classList.remove('active');
                    }
                }
                loadOverviewData();
                loadHistoryData();
            } else if (data.type === "engine_info_updated") {
                applyEngineMeta(data.data);
            }
        } catch (e) {
            console.error("WebSocket message parse error:", e);
        }
    };

    ws.onclose = function () {
        setTimeout(connectWebSocket, 2000);
    };
}

// ------------------------------------------------------------------------------
// Launch GUI Search
// ------------------------------------------------------------------------------
async function launchGuiSearch() {
    const usernameInput = document.getElementById('gui-username-input');
    const username = (usernameInput?.value || '').trim();
    if (!username) {
        alert("Please enter a target username.");
        usernameInput?.focus();
        return;
    }

    const tokens = buildCommandTokens();
    const cmdString = tokens.join(" ");

    // Prepare GUI Live Output
    const guiOutput = document.getElementById('gui-live-output');
    if (guiOutput) {
        guiOutput.innerHTML = "";
    }
    const dot = document.getElementById('gui-status-dot');
    if (dot) dot.classList.add('active');

    appendGuiLine(`$ ${cmdString}`);

    // Build payload containing exact tokens and explicit option map
    const payload = {
        username: username,
        tokens: tokens,
        all_sites: document.getElementById('opt-allsites')?.checked || false,
        use_top: document.getElementById('opt-use-top')?.checked || false,
        top_sites: parseInt(document.getElementById('opt-top')?.value || '500'),
        use_idtype: document.getElementById('opt-use-idtype')?.checked || false,
        id_type: document.getElementById('opt-idtype')?.value || 'username',
        permute: document.getElementById('opt-permute')?.checked || false,
        cloudflare_bypass: document.getElementById('opt-cf-bypass')?.checked || false,
        no_recursion: document.getElementById('opt-no-recursion')?.checked || false,
        no_progressbar: document.getElementById('opt-no-progressbar')?.checked || false,
        use_timeout: document.getElementById('opt-use-timeout')?.checked || false,
        timeout: parseInt(document.getElementById('opt-timeout')?.value || '15'),
        use_tags: document.getElementById('opt-use-tags')?.checked || false,
        tags: (document.getElementById('opt-tags')?.value || '').trim() ? [document.getElementById('opt-tags').value.trim()] : [],
        report_html: document.getElementById('rep-html')?.checked || false,
        report_pdf: document.getElementById('rep-pdf')?.checked || false,
        pdf_style: document.getElementById('opt-pdf-style')?.value || 'default',
        report_json: document.getElementById('rep-json')?.checked || false,
        report_csv: document.getElementById('rep-csv')?.checked || false,
        report_txt: document.getElementById('rep-txt')?.checked || false,
        report_md: document.getElementById('rep-md')?.checked || false,
        report_graph: document.getElementById('rep-graph')?.checked || false,
        report_xmind: document.getElementById('rep-xmind')?.checked || false
    };

    try {
        const res = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            guiActiveJobId = data.job_id;
            appendGuiLine(`[*] Investigation #${data.job_id} initiated. Engine streaming output below...\n`);
        } else {
            alert(data.detail || "Error starting search");
            if (dot) dot.classList.remove('active');
        }
    } catch (err) {
        alert("Failed to connect to backend engine.");
        if (dot) dot.classList.remove('active');
    }
}

// ------------------------------------------------------------------------------
// Terminal Interactive Input Handler
// ------------------------------------------------------------------------------
function initTerminalInput() {
    const termInput = document.getElementById('term-input');
    if (!termInput) return;

    termInput.addEventListener('keydown', async function (e) {
        if (e.key === 'Enter') {
            const cmd = termInput.value.trim();
            if (!cmd) return;
            terminalHistory.push(cmd);
            historyIndex = terminalHistory.length;

            appendTerminalLine(`\n$ ${cmd}`);
            termInput.value = '';

            if (cmd.toLowerCase() === 'clear') {
                clearTerminal();
                return;
            }

            try {
                const res = await fetch('/api/terminal/execute', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command: cmd })
                });
                const data = await res.json();
                if (data.output) appendTerminalLine(data.output);
                if (data.action === "open_investigation") viewInvestigation(data.job_id);
            } catch (err) {
                appendTerminalLine("[!] Communication error with backend.");
            }
        } else if (e.key === 'ArrowUp') {
            if (historyIndex > 0) {
                historyIndex--;
                termInput.value = terminalHistory[historyIndex];
            }
            e.preventDefault();
        } else if (e.key === 'ArrowDown') {
            if (historyIndex < terminalHistory.length - 1) {
                historyIndex++;
                termInput.value = terminalHistory[historyIndex];
            } else {
                historyIndex = terminalHistory.length;
                termInput.value = '';
            }
            e.preventDefault();
        }
    });
}

// ------------------------------------------------------------------------------
// Engine Metadata & Metrics
// ------------------------------------------------------------------------------
function applyEngineMeta(meta) {
    if (!meta) return;
    currentEngineMeta = meta;
    const count = meta.sites_count || 4990;
    const countFmt = meta.sites_count_formatted || count.toLocaleString();

    const metricSites = document.getElementById('metric-supported-sites');
    if (metricSites) metricSites.innerText = `${countFmt} max`;

    const labelAll = document.getElementById('label-allsites-text');
    if (labelAll) labelAll.innerText = ` Search ALL Supported Sites (${countFmt} sites)`;

    const topInput = document.getElementById('opt-top');
    if (topInput) topInput.max = count;

    const badge = document.getElementById('sidebar-engine-badge');
    if (badge) {
        const commitStr = meta.commit ? ` (${meta.commit})` : '';
        badge.innerText = `OSINT v${meta.version || '0.6.5'}${commitStr}`;
    }
}

async function loadOverviewData() {
    try {
        const res = await fetch('/api/overview');
        const data = await res.json();
        const searchesEl = document.getElementById('metric-searches');
        if (searchesEl) searchesEl.innerText = data.total_searches;

        const tasksEl = document.getElementById('metric-tasks');
        if (tasksEl) tasksEl.innerText = data.active_tasks;

        const foundEl = document.getElementById('metric-found');
        if (foundEl) foundEl.innerText = data.total_found || 0;

        if (data.engine_meta) {
            applyEngineMeta(data.engine_meta);
        } else if (data.supported_sites && document.getElementById('metric-supported-sites')) {
            document.getElementById('metric-supported-sites').innerText = data.supported_sites.toLocaleString() + " max";
        }

        const histRes = await fetch('/api/history');
        const history = await histRes.json();
        const recentBody = document.getElementById('overview-recent-body');
        if (!recentBody) return;
        recentBody.innerHTML = '';

        history.slice(0, 8).forEach(job => {
            recentBody.innerHTML += `
                <tr class="clickable-row" onclick="viewInvestigation(${job.id})">
                    <td style="font-family: var(--font-term); color: var(--accent-gold);">#${job.id}</td>
                    <td style="font-weight: 600;">${escapeHtml(job.username)}</td>
                    <td>${job.created_at || ''}</td>
                    <td><span class="badge badge-${job.status}">${job.status}</span></td>
                    <td style="font-family: var(--font-term);">${job.found_sites || 0}</td>
                    <td><button class="btn-danger" onclick="deleteJob(event, ${job.id})">Delete</button></td>
                </tr>
            `;
        });
    } catch (e) {
        console.error("Error loading overview data:", e);
    }
}

async function loadHistoryData() {
    try {
        const res = await fetch('/api/history');
        const history = await res.json();
        const tbody = document.getElementById('history-table-body');
        const reportsContainer = document.getElementById('reports-list-container');
        if (!tbody) return;

        tbody.innerHTML = '';
        if (reportsContainer) reportsContainer.innerHTML = '';

        history.forEach(job => {
            tbody.innerHTML += `
                <tr class="clickable-row" onclick="viewInvestigation(${job.id})">
                    <td style="font-family: var(--font-term); color: var(--accent-gold);">#${job.id}</td>
                    <td style="font-weight: 600;">${escapeHtml(job.username)}</td>
                    <td>${job.created_at || ''}</td>
                    <td style="font-weight: 700; color: var(--accent-gold);">${job.found_sites || 0}</td>
                    <td><span class="badge badge-${job.status}">${job.status}</span></td>
                    <td><button class="btn-danger" onclick="deleteJob(event, ${job.id})">Delete</button></td>
                </tr>
            `;

            if (reportsContainer && job.reports_generated && job.reports_generated.length > 0) {
                const jobFolder = `/reports/job_${job.id}`;
                job.reports_generated.forEach(rtype => {
                    let filename = `report_${job.username}.${rtype}`;
                    let displayName = rtype.toUpperCase();
                    if (rtype === "internal_html") {
                        filename = `report_${job.username}_internal.html`;
                        displayName = "INTERNAL DOSSIER";
                    } else if (rtype === "graph") {
                        filename = `report_${job.username}_graph.html`;
                        displayName = "GRAPH VISUALIZER";
                    } else if (rtype === "html") {
                        displayName = "HTML REPORT";
                    } else if (rtype === "pdf") {
                        displayName = "PDF DOSSIER";
                    } else if (rtype === "json") {
                        displayName = "JSON EXPORT";
                    } else if (rtype === "csv") {
                        displayName = "CSV DATA";
                    } else if (rtype === "txt") {
                        displayName = "TXT SUMMARY";
                    } else if (rtype === "md") {
                        displayName = "MARKDOWN REPORT";
                    } else if (rtype === "xmind") {
                        displayName = "XMIND MINDMAP";
                    }
                    const targetReport = `${jobFolder}/${filename}`;
                    reportsContainer.innerHTML += `
                        <div class="metric-card clickable-row" style="padding: 14px; margin-bottom: 8px;" onclick="previewReport('${targetReport}', '${rtype}', '${displayName}', '${escapeHtml(job.username)}')">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <h4 style="color: var(--accent-gold); font-size: 0.95rem;">${escapeHtml(job.username)}</h4>
                                <span class="badge" style="background: rgba(234, 179, 8, 0.15); color: var(--accent-gold); font-size: 0.7rem;">${displayName}</span>
                            </div>
                            <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 4px;">Job #${job.id} • ${job.created_at || ''}</div>
                        </div>
                    `;
                });
            }
        });
    } catch (e) {
        console.error("Error loading history data:", e);
    }
}

async function deleteJob(event, jobId) {
    event.stopPropagation();
    if (!confirm(`Permanently delete Investigation #${jobId}?`)) return;
    try {
        await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
        loadOverviewData();
        loadHistoryData();
        resetReportViewer();
    } catch (err) {
        alert("Failed to delete job.");
    }
}

async function previewReport(url, rtype, displayName, username) {
    const container = document.getElementById('report-viewport-container');
    if (!container) return;

    rtype = (rtype || '').toLowerCase();
    displayName = displayName || 'REPORT';
    username = username || '';

    // Header Toolbar
    const toolbar = `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 18px; background: #101015; border-bottom: 1px solid var(--border-color); flex-shrink: 0;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span class="badge" style="background: rgba(234, 179, 8, 0.2); color: var(--accent-gold);">${displayName}</span>
                <span style="font-weight: 700; color: #fff; font-size: 0.9rem;">${escapeHtml(username)}</span>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                <a href="${url}" target="_blank" class="term-btn" style="text-decoration: none; display: inline-flex; align-items: center; gap: 4px;">↗ Open in Tab</a>
                <a href="${url}" download class="term-btn" style="text-decoration: none; display: inline-flex; align-items: center; gap: 4px;">⬇ Download</a>
            </div>
        </div>
    `;

    if (rtype === 'xmind' || url.endsWith('.xmind')) {
        container.innerHTML = `
            ${toolbar}
            <div style="padding: 40px; text-align: center; margin: auto;">
                <div style="font-size: 3rem; margin-bottom: 10px;">🧠</div>
                <h3 style="color: var(--accent-gold); margin-bottom: 8px;">XMind Mindmap Ready</h3>
                <p style="color: var(--text-dim); max-width: 480px; margin: auto; font-size: 0.9rem;">
                    This investigation was mapped into an XMind mindmap XML archive. You can download the file and open it in XMind or any compatible MindMap application.
                </p>
                <div style="margin-top: 25px;">
                    <a href="${url}" download class="btn-primary" style="text-decoration: none; padding: 10px 24px;">Download .xmind File</a>
                </div>
            </div>
        `;
        return;
    }

    if (rtype === 'pdf' || url.endsWith('.pdf')) {
        container.innerHTML = `
            ${toolbar}
            <embed src="${url}" type="application/pdf" width="100%" height="100%" style="border:none; flex-grow: 1;" />
        `;
        return;
    }

    if (rtype === 'html' || rtype === 'graph' || rtype === 'internal_html' || url.endsWith('.html')) {
        container.innerHTML = `
            ${toolbar}
            <iframe src="${url}" style="width:100%; height:100%; border:none; flex-grow: 1; background: #0c0c0e;"></iframe>
        `;
        return;
    }

    // Text-based files (txt, csv, json, md)
    try {
        container.innerHTML = `
            ${toolbar}
            <div style="padding: 20px; color: var(--text-dim); text-align: center; margin: auto;">Loading document preview...</div>
        `;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const rawText = await res.text();
        let formattedText = rawText;

        if (rtype === 'json' || url.endsWith('.json')) {
            try {
                formattedText = JSON.stringify(JSON.parse(rawText), null, 2);
            } catch (e) {
                formattedText = rawText;
            }
        }

        container.innerHTML = `
            ${toolbar}
            <pre class="terminal-body" style="flex-grow: 1; margin: 0; padding: 20px; white-space: pre-wrap; word-break: break-all; user-select: text; background: #050507; overflow-y: auto;">${escapeHtml(formattedText)}</pre>
        `;
    } catch (err) {
        container.innerHTML = `
            ${toolbar}
            <div style="padding: 40px; text-align: center; margin: auto; color: var(--status-red);">
                <h4>Failed to load preview</h4>
                <p style="color: var(--text-dim); margin-top: 8px;">${escapeHtml(err.message)}</p>
                <a href="${url}" download class="term-btn" style="margin-top: 15px; display: inline-block;">Download File Directly</a>
            </div>
        `;
    }
}

function resetReportViewer() {
    const container = document.getElementById('report-viewport-container');
    if (container) {
        container.innerHTML = `<div style="padding: 20px; color: #718096; text-align: center; margin: auto;">Select a report from the left panel to preview</div>`;
    }
}

async function viewInvestigation(jobId) {
    try {
        const res = await fetch(`/api/jobs/${jobId}`);
        const job = await res.json();
        document.getElementById('inv-modal-title').innerText = `Investigation Dossier #${job.id}: ${job.username}`;
        document.getElementById('inv-modal-stats').innerHTML = `
            <div>STATUS: <span class="badge badge-${job.status}">${job.status}</span></div>
            <div>FOUND: <span style="color: var(--accent-gold);">${job.found_sites || 0}</span></div>
        `;

        const logsDiv = document.getElementById('inv-terminal-logs');
        logsDiv.innerHTML = "";
        
        const foundLines = [];
        job.logs.forEach(l => {
            const parts = l.split('\r');
            parts.forEach(p => {
                const part = p.trim();
                if ((part.includes("[+] ") || part.includes("[++] ") || part.includes("[?] ")) && 
                    part.includes("http") && 
                    !part.includes("MAIGRET") && 
                    !part.includes("Using sites") && 
                    !part.includes("Donate")) {
                    foundLines.push(part);
                } else if (part.includes("FOUND") && !part.includes("NOT FOUND") && !part.includes("Starting")) {
                    foundLines.push(part);
                }
            });
        });

        if (foundLines.length === 0) {
            logsDiv.innerHTML = "<span style='color: var(--text-dim);'>No positive matches found in logs.</span>";
        } else {
            foundLines.forEach(line => {
                const urlMatch = line.match(/(https?:\/\/[^\s]+)/);
                if (urlMatch) {
                    const url = urlMatch[1];
                    let prefix = line.substring(0, urlMatch.index).trim();
                    prefix = prefix.replace(/^\[[\+\?\*]+\]\s*/, '').replace(/[:\-–—>]+$/, '').trim();
                    logsDiv.innerHTML += `
                        <div style="padding: 8px 12px; background: rgba(234, 179, 8, 0.05); border: 1px solid rgba(234, 179, 8, 0.15); border-radius: 6px; display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 4px;">
                            <span style="color: var(--accent-gold); font-weight: 700; min-width: 140px;">${escapeHtml(prefix || 'Profile')}</span>
                            <a href="${url}" target="_blank" style="color: #38bdf8; text-decoration: underline; word-break: break-all; font-family: var(--font-term); font-size: 0.85rem;">${escapeHtml(url)}</a>
                        </div>
                    `;
                } else {
                    logsDiv.innerHTML += `<div><span style="color: var(--accent-gold); font-weight: bold;">${escapeHtml(line)}</span></div>`;
                }
            });
        }

        const linksDiv = document.getElementById('inv-report-links');
        linksDiv.innerHTML = '';

        if (job.reports_generated && job.reports_generated.length > 0) {
            const jobFolder = `/reports/job_${job.id}`;
            job.reports_generated.forEach(rtype => {
                let filename = `report_${job.username}.${rtype}`;
                let displayName = rtype.toUpperCase();

                if (rtype === "internal_html") {
                    filename = `report_${job.username}_internal.html`;
                    displayName = "INTERNAL DOSSIER";
                } else if (rtype === "graph") {
                    filename = `report_${job.username}_graph.html`;
                    displayName = "GRAPH VISUALIZER";
                } else if (rtype === "html") {
                    displayName = "HTML REPORT";
                } else if (rtype === "pdf") {
                    displayName = "PDF DOSSIER";
                } else if (rtype === "json") {
                    displayName = "JSON EXPORT";
                } else if (rtype === "csv") {
                    displayName = "CSV DATA";
                } else if (rtype === "txt") {
                    displayName = "TXT SUMMARY";
                } else if (rtype === "md") {
                    displayName = "MARKDOWN REPORT";
                } else if (rtype === "xmind") {
                    displayName = "XMIND MINDMAP";
                }

                const path = `${jobFolder}/${filename}`;
                const a = document.createElement('a');
                a.href = path;
                a.innerText = `Download ${displayName}`;
                a.setAttribute('download', '');
                linksDiv.appendChild(a);
            });
        }
        openModal('investigationModal');
    } catch (e) {
        alert("Failed to load investigation details.");
    }
}

// ------------------------------------------------------------------------------
// Initialization
// ------------------------------------------------------------------------------
window.onload = function () {
    connectWebSocket();
    initTerminalInput();
    fetch('/api/engine/info').then(r => r.json()).then(applyEngineMeta).catch(() => {});
    loadOverviewData();
    loadHistoryData();

    // Attach real-time input and change listeners for Command Preview
    const usernameInput = document.getElementById('gui-username-input');
    if (usernameInput) {
        usernameInput.addEventListener('input', updateCommandPreview);
        usernameInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') launchGuiSearch();
        });
    }

    const previewTriggers = [
        'opt-allsites', 'opt-use-top', 'opt-top', 'opt-use-idtype', 'opt-idtype',
        'opt-permute', 'opt-cf-bypass', 'opt-no-recursion', 'opt-no-progressbar',
        'opt-use-timeout', 'opt-timeout', 'opt-use-tags', 'opt-tags',
        'rep-html', 'rep-pdf', 'rep-json', 'rep-csv', 'rep-txt', 'rep-md', 'rep-graph', 'rep-xmind'
    ];
    previewTriggers.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', updateCommandPreview);
            el.addEventListener('input', updateCommandPreview);
        }
    });

    updateCommandPreview();
};
