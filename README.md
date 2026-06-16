# HAR vs JMeter — Gap Analyser

> Compare real browser load time (HAR files) with JMeter results — side by side, in a rich HTML report. No plugin required.

[![Python 3.7+](https://img.shields.io/badge/Python-3.7%2B-green)](https://python.org/)
[![JMeter 5.x](https://img.shields.io/badge/JMeter-5.x-orange)](https://jmeter.apache.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## The question this tool answers

> **JMeter says your API responds in 350ms. The browser says the same call took 500ms. Which one do you trust?**

Both — they're measuring **different things**:

| | JMeter | HAR |
|---|---|---|
| **Measures** | How long each scripted request took | How long the user actually waited |
| **Sees** | What you explicitly scripted | Everything the browser fired — including 3rd party scripts, lazy loads, render-triggered calls |
| **When slower** | Backend under concurrent load — DB contention, cold caches, GC pauses | Browser overhead — DNS, SSL, connection limits, real network |

**Passing your JMeter test doesn't mean your users are happy.** This tool bridges the gap.

---

## Quick start (3 steps)

**Step 1 — Export a HAR file from Chrome/Firefox**
- Open DevTools → Network tab
- Navigate through your app **2–3 times** (warm cache = realistic returning user)
- Right-click any request → **Save all as HAR with content**

**Step 2 — Export a JMeter Summary Report CSV**
- Add a **Summary Report** listener to your test plan
- Run your test
- Right-click the Summary Report → **Save Table Data** → save as `.csv`

**Step 3 — Run the comparison**
```bash
python har_vs_jmeter.py your_file.har summary_report.csv report.html
```

Open `report.html` — done.

---

## What the report shows

- **4 stat cards** — HAR total load time, request count, JMeter samplers, matched count
- **Request-level comparison table** — HAR time vs JMeter avg, diff, dual bar chart, match score
- **Unmatched HAR requests** — 3rd party scripts, fonts, ad networks the browser loaded that JMeter never saw
- **Unmatched JMeter samplers** — samplers with no HAR equivalent
- **"Why the diff?" reference** — built into every report, explains whether browser overhead or backend load is the likely cause

---

## Requirements

- Python 3.7+ (standard library only — no `pip install` needed)
- A `.har` file exported from Chrome or Firefox DevTools
- A JMeter **Summary Report CSV** (exported from the Summary Report listener)

---

## URL Matching

HAR requests are matched to JMeter sampler labels by URL path similarity.

| HAR URL | JMeter Label | Match |
|---|---|---|
| `/api/session` | `/api/session` | ✅ Exact (score 100) |
| `/api/session` | `/api/session-1` | ✅ Recorder suffix auto-stripped |
| `/SearchHotel.php` | `/SearchHotel.php-85` | ✅ Recorder counter stripped |
| `/api/session` (×2 in HAR) | `/api/session` | ✅ Both HAR hits matched (many-to-one) |
| `ads.example.net/ad.js` | — | → Unmatched HAR (3rd party) |

---

## Sample files

The `examples/` folder has a ready-to-use demo set:

| File | Description |
|---|---|
| `demo.har` | 10 browser requests — 3 APIs + static assets + a slow 900ms 3rd-party ad script |
| `demo_summary.csv` | JMeter Summary Report for the 3 API samplers |
| `demo_test.jmx` | Minimal JMeter test plan matching the HAR |

**Try it:**
```bash
python har_vs_jmeter.py examples/demo.har examples/demo_summary.csv examples/demo_report.html
```

---

## Why the diff? (built into every report)

**HAR > JMeter — the browser pays a tax JMeter doesn't**
- DNS + SSL/TLS handshake (JMeter reuses keep-alive connections)
- Render-blocking dependencies
- Per-host connection limits (~6 concurrent)
- Real network conditions — latency, packet loss on the user's actual connection
- 3rd party scripts you never scripted

**JMeter > HAR — the backend pays a tax HAR doesn't**
- Concurrent load — many virtual users hammering the backend simultaneously
- DB connection pool exhaustion
- Lock contention — concurrent writes cause locks a single session never triggers
- Cold vs warm caches under load
- GC pauses / CPU saturation

---

## JMeter Listener plugin (optional)

A JMeter GUI Listener plugin is also available in [Releases](../../releases) for those who prefer a UI wrapper inside JMeter.

> **Note:** The standalone Python script above is the recommended approach. The plugin wraps the same Python engine — the standalone script is simpler and more reliable for most workflows.

---

## Project structure

```
HAR_vs_Jmeter/
├── har_vs_jmeter.py        ← main Python script (run this)
├── README.md
├── examples/
│   ├── demo.har
│   ├── demo_summary.csv
│   └── demo_test.jmx
└── plugin/                 ← optional JMeter GUI plugin
    ├── pom.xml
    └── src/
```

---

## Built by

**Visvashwarr Venugopal** — Performance Engineer, 11+ years across Oracle and TCS. Now freelancing.

- 🔗 LinkedIn: [linkedin.com/in/visvashwarrvenugopal](https://www.linkedin.com/in/visvashwarrvenugopal/)

---

## License

MIT — free to use, modify, and distribute. Attribution appreciated.
