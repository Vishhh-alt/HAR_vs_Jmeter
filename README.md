# HAR vs JMeter Listener

> Compare real browser load time (HAR files) with JMeter sampler results — side by side, inside JMeter, automatically.

[![JMeter 5.x](https://img.shields.io/badge/JMeter-5.x-orange)](https://jmeter.apache.org/)
[![Java 11+](https://img.shields.io/badge/Java-11%2B-blue)](https://openjdk.org/)
[![Python 3.7+](https://img.shields.io/badge/Python-3.7%2B-green)](https://python.org/)
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

**Passing your JMeter test doesn't mean your users are happy.** This plugin bridges the gap.

---

## Features

- 🔌 **Native JMeter Listener** — installs in one step, appears in JMeter's GUI like any built-in listener
- 🔄 **Two modes** — Live (auto-collects during test run) or Offline (compare saved HAR + CSV anytime)
- 🔗 **Smart URL matching** — matches HAR requests to JMeter samplers by path, strips recorder-appended suffixes (`-1`, `_2`, `(3)`) automatically, supports many-to-one (repeated calls to the same endpoint)
- 📊 **Rich HTML report** — waterfall view, diff per request, match score, and a built-in "Why the diff?" reference guide
- 🌐 **Unmatched HAR section** — surfaces 3rd party scripts, fonts, ad networks, and browser-discovered resources that JMeter never saw

---

## Installation

### Requirements
- JMeter 5.x
- Java 11+
- Python 3.7+ (standard library only — no `pip install` needed)

### Option A — Pre-built JAR *(recommended)*

1. Go to [Releases](../../releases) → download `har-jmeter-listener-1.0.0-plugin.jar`
2. Copy to `<JMeter>/lib/ext/`
3. **Restart JMeter**
4. Right-click Thread Group → **Add → Listener → HAR vs JMeter Listener**

### Option B — Build from source

```bash
git clone https://github.com/visvashwarrvenugopal/har-jmeter-listener.git
cd har-jmeter-listener
mvn clean package
# Output: target/har-jmeter-listener-1.0.0-plugin.jar
```

---

## Usage

### Live mode
Collects sample results during the test run. Report generates and opens automatically when the test ends.

1. Select **Live** mode in the listener panel
2. Set **HAR file path** and **Output folder**
3. Run your test — the report auto-opens in your browser

### Offline mode
Compare any saved HAR file against any existing JMeter Summary Report CSV. No test run needed — useful for consulting, historical comparisons, or re-running analysis on old data.

1. Select **Offline** mode
2. Pick your `.har` file and the JMeter **Summary Report CSV** (exported from JMeter's Summary Report listener)
3. Click **Run Comparison Now**

### Capturing a HAR file

1. Open **Chrome or Firefox** → press **F12** → Network tab
2. Navigate through your application **2–3 times** (warm cache = realistic returning user, not cold-start noise)
3. Right-click any request → **Save all as HAR with content**

---

## URL Matching

HAR requests are matched to JMeter sampler labels by URL path similarity.

| HAR URL | JMeter Label | Match |
|---|---|---|
| `/api/session` | `/api/session` | ✅ Exact (score 100) |
| `/api/session` | `/api/session-1` | ✅ Recorder suffix auto-stripped |
| `/SearchHotel.php` | `/SearchHotel.php-85` | ✅ Recorder counter stripped |
| `/api/session` (×2) | `/api/session` | ✅ Both HAR hits matched (many-to-one) |
| `ads.example.net/ad.js` | — | → Unmatched HAR (3rd party) |
| `/api/products/4521` | — | → Unmatched HAR (no sampler) |

Unmatched HAR requests (3rd party scripts, browser-only static assets) are shown in a separate section — these are often where the most interesting performance findings hide.

---

## Sample files

The `examples/` folder contains a ready-to-use demo set (a fictional content site with 10 browser requests including a slow 3rd-party ad script):

| File | Description |
|---|---|
| `demo.har` | 10 browser requests — 3 API calls, static assets, and a 900ms 3rd-party ad script |
| `demo_summary.csv` | JMeter Summary Report for the 3 API samplers |
| `demo_test.jmx` | Minimal JMeter test plan matching the HAR |

**To try it:** open `demo_test.jmx` in JMeter, add the listener, select **Offline** mode, point at `demo.har` + `demo_summary.csv`, click **Run Comparison Now**.

---

## Why the diff? (built into the report)

Every report includes a reference guide explaining the gap in either direction:

**HAR > JMeter — the browser pays a tax JMeter doesn't**
- DNS + SSL/TLS handshake (JMeter reuses keep-alive connections)
- Render-blocking dependencies — browser must parse HTML/CSS/JS before firing the request
- Per-host connection limits (~6 concurrent) — JMeter threads aren't bound
- Real network conditions — latency, packet loss on the user's actual connection
- 3rd party scripts — ad networks, analytics, chat widgets that were never scripted

**JMeter > HAR — the backend pays a tax HAR doesn't**
- Concurrent load — many virtual users hammering the backend simultaneously
- DB connection pool exhaustion — requests queue for a database connection
- Lock contention — concurrent writes cause row locks a single session never triggers
- Cold vs warm caches — many threads with varied data may miss server-side caches
- GC pauses / CPU saturation under sustained load

---

## Project structure

```
har-jmeter-listener/
├── pom.xml
├── README.md
├── examples/
│   ├── demo.har
│   ├── demo_summary.csv
│   └── demo_test.jmx
└── src/main/
    ├── java/com/visvashwarr/jmeter/listener/
    │   ├── HarVsJmeterListener.java        ← JMeter GUI Listener
    │   └── HarVsJmeterListenerElement.java  ← TestElement (engine-side)
    └── resources/
        └── har_vs_jmeter_core.py           ← Python report engine (bundled in JAR)
```

---

## Built by

**Visvashwarr Venugopal** — Performance Engineer with 11+ years across Oracle and TCS.
Now freelancing. Available for performance audits, load test strategy, team training, and 1:1 mentoring.

- LinkedIn: [linkedin.com/in/visvashwarrvenugopal](https://www.linkedin.com/in/visvashwarrvenugopal/)
- Topmate: *(coming soon)*

---

## License

MIT — free to use, modify, and distribute. Attribution appreciated.
