<div align="center">

  <img src="logos/maigret%20logo.png" alt="Maigret OSINT Suite" width="450">

  # Maigret 2.0 OSINT Intelligence Suite
  ### Modern Interactive Web Dashboard & Real-Time Dossier Engine

  [![Python Version](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
  [![Sites Supported](https://img.shields.io/badge/Sites_Supported-3%2C000%2B-EAB308?style=for-the-badge&logo=target&logoColor=black)](https://github.com/soxoj/maigret)
  [![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
  [![Engine](https://img.shields.io/badge/Engine-Maigret%20v0.6.5-6366F1?style=for-the-badge)](https://github.com/soxoj/maigret)
  [![Citation](https://img.shields.io/badge/Cite-CITATION.cff-blue?style=for-the-badge)](tools/maigret/CITATION.cff)

  <p align="center">
    <b>A premier OSINT investigation workstation combining the power of the Maigret engine with an ultra-responsive web dashboard, live WebSocket streaming terminal, and automated multi-format report generator.</b>
  </p>

</div>

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Platform Architecture](#-platform-architecture)
- [Quick Start](#-quick-start)
- [Dashboard Walkthrough](#-dashboard-walkthrough)
- [CLI & Interactive Terminal Console](#-cli--interactive-terminal-console)
- [Supported Identifier Types](#-supported-identifier-types)
- [Report Formats](#-report-formats)
- [Configuration & Options](#-configuration--options)
- [Troubleshooting & Windows Setup](#-troubleshooting--windows-setup)
- [Citation & Attribution](#-citation--attribution)
- [Credits & Acknowledgements](#-credits--acknowledgements)

---

## 🔍 Overview

**Maigret 2.0** is an enterprise-grade OSINT (Open Source Intelligence) investigation platform designed to identify, collect, and analyze digital footprints across thousands of online platforms using **username only**.

Building on the industry-standard [Maigret](https://github.com/soxoj/maigret) engine, this platform introduces:
- A sleek, cyber-themed **Interactive Web Dashboard** featuring glassmorphism and curated dark mode palettes.
- A **Real-Time Terminal Console** streamed via WebSockets, replicating a native terminal with full CLI flag support.
- **Dossier Management & Embedded Previews** with instant viewing for HTML, PDF, JSON, CSV, and TXT exports.
- Robust, loop-agnostic asynchronous process execution tailored for seamless operation on Windows and Unix alike.

---

## ⚡ Key Features

- **🌐 3,000+ Platforms Supported**: Search the top 500 Alexa-ranked platforms by default, or expand to the complete 3,000+ site database.
- **⚡ Live WebSocket Telemetry**: Watch investigations unfold in real time with line-by-line streaming, live match counters, and colored output tags.
- **📑 Multi-Format Report Generation**: Automatically generate PDF reports, HTML dossiers, CSV matrices, JSON files, plain text, and custom intelligence briefings.
- **🧬 Deep Account Extraction**: Powered by `socid-extractor` to recursively extract avatar URLs, linked social profiles, IDs, and bios from returned profiles.
- **🎯 Alternative Identifier Support**: Scan with specialized IDs including Steam IDs, VKontakte IDs, Google Gaia IDs, Yandex Public IDs, and more.
- **🔄 Universal Event-Loop Compatibility**: Re-engineered subprocess architecture utilizing `subprocess.Popen` and asynchronous non-blocking thread streaming to eliminate Windows `NotImplementedError` issues.
- **🛡️ Built-in Resilience**: Configurable request timeouts, Cloudflare challenge evasion, username permutations, and isolated per-investigation directories.

---

## 🏗️ Platform Architecture

```text
maigret-testing-2.0/
├── logos/                         # High-resolution logos & UI iconography
│   ├── maigret logo shield.png    # Shield badge & tab favicon
│   └── maigret logo.png           # Primary banner emblem
├── reports/                       # Isolated investigation output folders (job_<id>/)
├── static/                        # Frontend assets
│   ├── index.html                 # Unified single-page application dashboard
│   ├── script.js                  # Modular script extensions
│   └── styles.css                 # Custom design tokens & themes
├── tools/
│   └── maigret/                   # Full Maigret engine source & site database
├── main.py                        # FastAPI application & real-time WebSocket server
├── search_history.json            # Persistent investigation history datastore
└── README.md                      # Platform documentation
```

---

## 🚀 Quick Start

### 1. Prerequisites
Ensure you have **Python 3.10+** and **Git** installed on your system.

### 2. Installation
Clone the repository and install the application dependencies:

```powershell
# Navigate to the workspace
cd "maigret-testing-2.0"

# Install web application requirements
py -m pip install fastapi "uvicorn[standard]" websockets pydantic

# Install PDF generation engine (optional, for PDF export)
py -m pip install xhtml2pdf

# Install Maigret engine in editable mode
py -m pip install -e ./tools/maigret
```

### 3. Launch the Server
Start the Uvicorn application server:

```powershell
py main.py
```
*(Or use `python main.py` if python is registered in your system PATH).*

### 4. Open the Dashboard
Navigate your web browser to:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 🖥️ Dashboard Walkthrough

### ◈ Overview
Displays aggregate metrics across your workstation:
- **Total Investigations**: Lifetime scan counter.
- **Sites Supported**: Live platform database size (~3,000+).
- **Active Tasks**: Real-time count of currently running searches.
- **Profiles Uncovered**: Cumulative verified accounts discovered.
- **Recent Dossiers**: Clickable table of recent investigations with quick access to results and deletion controls.

<div align="center">
  <img src="logos/maigret%20logo%20shield.png" width="100" alt="Maigret Shield">
</div>

### ⌕ Launch Investigation (GUI)
A structured control center for targeted queries:
- **Target Username**: Input the handle to investigate.
- **Scope**: Toggle between *Search ALL Sites (~3,000+)* or define a specific *Top Sites* rank limit (e.g., 500).
- **Identifier Type**: Choose between standard usernames or platform-specific IDs (Steam, VK, Yandex, etc.).
- **Options & Modifiers**: Enable username permutations, Cloudflare bypass, timeouts, and category tags (`photo`, `dating`, `us`).
- **Reports**: Select desired export formats (HTML, PDF, JSON, CSV, TXT, or custom Internal Dossier format).
- **Live Output**: Real-time execution console displaying live scan results.

### ◷ Search History
- Complete historical ledger of every query.
- Displays Job ID, target handle, execution timestamp, matches discovered, and status badges (`RUNNING`, `COMPLETED`, `CANCELLED`).
- Click any investigation row to open the **Investigation Dossier Modal**.

### 📄 Reports Viewer
- Split-pane native viewer.
- **Left Panel**: Lists all generated reports across investigations with format badges (`HTML`, `PDF`, `JSON`, `CSV`, `TXT`).
- **Right Panel**: Embedded previewer allowing you to read full PDF and HTML dossiers directly within the browser without leaving the dashboard.

---

## ⌨️ CLI & Interactive Terminal Console

The dashboard includes a full-featured, browser-based **Terminal Console** synchronized with the backend engine via WebSockets. It replicates the native command-line experience with interactive arrow-key history and styled output.

### Native Maigret CLI Commands
Any standard `maigret` command can be executed directly:

```bash
# Display full CLI manual and argument documentation
$ maigret --help

# Check Maigret engine and dependency versions
$ maigret --version

# List all supported sites and platforms
$ maigret --list-sites

# View database metrics and platform statistics
$ maigret --stats

# Perform a quick scan on top 50 sites
$ maigret alice --top-sites 50

# Scan with HTML, PDF, and CSV reports generated
$ maigret bob --html --pdf --csv

# Search with tags and custom timeout
$ maigret charlie --tags photo,tech --timeout 20
```

### Dashboard Console Utilities
The terminal also includes dedicated management commands:

| Command | Description |
| :--- | :--- |
| `help` | Displays console command reference and usage tips |
| `jobs` / `investigations` | Lists recent investigation records in a formatted table |
| `open <id>` | Instantly opens the investigation dossier modal for job `#<id>` |
| `status` | Displays engine status and active job counts |
| `cancel` | Halts and terminates all active running investigations |
| `clear` | Clears the terminal screen |

---

## 🏷️ Supported Identifier Types

Maigret allows cross-referencing accounts using specific platform IDs rather than plain usernames:

| Identifier Key | Platform / Purpose | Example |
| :--- | :--- | :--- |
| `username` | Standard account handle (Default) | `john_doe` |
| `steam_id` | Valve Steam Community ID | `76561198000000000` |
| `vk_id` | VKontakte profile identifier | `12345678` |
| `ok_id` | Odnoklassniki account ID | `571234567890` |
| `yandex_public_id` | Yandex public profile key | `user-identifier` |
| `gaia_id` | Google Account Gaia ID | `102938475610293847561` |
| `bilibili_id` | Bilibili member number | `123456` |
| `yelp_userid` | Yelp reviewer identifier | `AbCdEf123456` |
| `orcid` | ORCID Researcher identifier | `0000-0002-1825-0097` |
| `qq_id` | Tencent QQ number | `10001` |
| `wikimapia_uid` | Wikimapia user number | `12345` |
| `uidme_uguid` | UID.me profile key | `987654` |

---

## 📊 Report Formats

When an investigation concludes, reports are saved to `reports/job_<id>/`:

- **HTML Report (`.html`)**: Beautiful, self-contained interactive report with links, screenshots, and visual metadata.
- **PDF Report (`.pdf`)**: Formatted printable PDF dossier suitable for distribution and formal casework.
- **JSON Export (`.json`)**: Machine-readable structured output including claimed sites, URLs, and extracted tags.
- **CSV Export (`.csv`)**: Tabular export ready for spreadsheet analysis or ingestion into SIEM tools.
- **TXT Export (`.txt`)**: Clean plaintext listing of confirmed profile links.
- **Internal Dossier (`_internal.html`)**: Executive summary template formatted with high-contrast intelligence branding.

---

## ⚙️ Configuration & Options

Key scan flags supported via GUI and CLI:

- `--top-sites <N>`: Limit search to top $N$ Alexa-ranked sites (e.g., 500).
- `--all-sites` / `-a`: Search every platform in the database (~3,000+).
- `--tags <tags>`: Comma-separated categories to target (e.g. `coding`, `music`, `finance`, `us`, `ru`).
- `--timeout <sec>`: HTTP timeout per connection (default: 15s - 30s).
- `--permute`: Generates variations of usernames (e.g., `user_name`, `user.name`).
- `--cloudflare-bypass`: Evasion module for Cloudflare JS challenges.
- `--no-progressbar`: Disables console progress bar for clean logging output.

---

## 🔄 Updating the Engine (`updates/update.py`)

Keep the embedded Maigret tool and its database of 4,900+ target platforms synchronized with upstream [soxoj/maigret](https://github.com/soxoj/maigret):

```powershell
# Run the automated updater from your terminal
py updates/update.py

# Optional: Check for updates without applying
py updates/update.py --check-only

# Optional: Force reset local modifications if any conflicts occur
py updates/update.py --force
```

*Tip: You can also type `update` directly into the web dashboard's Interactive Terminal Console.*

**What the updater does:**
1. **Source Synchronization**: Pulls the latest commits from upstream Git (`https://github.com/soxoj/maigret.git`).
2. **Dependency Refresh**: Re-indexes package dependencies and editable registrations.
3. **Sites Database Sync**: Refreshes site definitions and parsing signatures (4,900+ online targets).
4. **Cache Invalidation**: Cleans compiled `__pycache__` artifacts for instant reflection in the dashboard.

---

## 🛠️ Troubleshooting & Windows Setup

### 1. `Python was not found` on Windows
If Windows intercepts your `python` command with the Microsoft Store shortcut:
1. Use `py main.py` instead of `python main.py`.
2. Or go to **Windows Settings $\rightarrow$ Apps $\rightarrow$ Advanced app settings $\rightarrow$ App execution aliases** and switch **OFF** `python.exe` and `python3.exe`.

### 2. WebSocket 404 / Upgrade Warnings
If you see `Unsupported upgrade request` or `No supported WebSocket library detected`:
```powershell
py -m pip install "uvicorn[standard]" websockets
```

### 3. Missing PDF Dependencies
If PDF generation fails or gives warnings:
```powershell
py -m pip install xhtml2pdf
```

---

## 📚 Citation & Attribution

If you use this software or the underlying intelligence engine in academic research, security audits, investigative reporting, or derivative tools, please cite the upstream [Maigret](https://github.com/soxoj/maigret) project as requested by its authors:

### 📝 Text / APA Format
> Soxoj. *Maigret: Collect a dossier on a person by username from thousands of sites.* Software repository: [https://github.com/soxoj/maigret](https://github.com/soxoj/maigret) • Documentation: [https://maigret.readthedocs.io](https://maigret.readthedocs.io).

### 📄 Citation File Format (`CITATION.cff`)
A machine-readable citation specification compliant with CFF 1.2.0 is maintained in [`tools/maigret/CITATION.cff`](tools/maigret/CITATION.cff).

<details>
<summary><b>Click to expand <code>CITATION.cff</code></b></summary>

```yaml
cff-version: 1.2.0
message: "If you use this software, please cite it as below."
type: software
title: "Maigret"
abstract: "Collect a dossier on a person by username from thousands of sites."
authors:
  - name: "Soxoj"
    website: "https://github.com/soxoj"
repository-code: "https://github.com/soxoj/maigret"
url: "https://maigret.readthedocs.io"
license: MIT
keywords:
  - osint
  - username-search
  - social-media
  - investigation
```

</details>

---

## 📜 Credits & Acknowledgements

- **Core OSINT Engine**: [Maigret](https://github.com/soxoj/maigret) by [@soxoj](https://github.com/soxoj).
- **Metadata Extraction**: [socid-extractor](https://github.com/soxoj/socid_extractor).
- **Web Framework**: [FastAPI](https://fastapi.tiangolo.com/) by [@tiangolo](https://github.com/tiangolo).
- **ASGI Server**: [Uvicorn](https://www.uvicorn.org/).

---

<div align="center">
  <sub>Maigret 2.0 • For authorized security research, intelligence analysis, and personal footprint audits.</sub>
</div>