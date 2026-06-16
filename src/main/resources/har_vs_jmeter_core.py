import json
import csv
import os
import sys
from datetime import datetime, timedelta
from urllib.parse import urlparse


# ─────────────────────────────────────────────
# PARSE HAR
# ─────────────────────────────────────────────

def parse_har(har_path):
    with open(har_path, "r", encoding="utf-8-sig") as f:
        har_data = json.load(f)

    entries = har_data.get("log", {}).get("entries", [])
    if not entries:
        return [], 0.0

    start_times, end_times = [], []
    requests = []

    for entry in entries:
        started = datetime.fromisoformat(entry["startedDateTime"].replace("Z", "+00:00"))
        duration_ms = max(entry.get("time", 0), 0)
        end_time = started + timedelta(milliseconds=duration_ms)

        start_times.append(started)
        end_times.append(end_time)

        url = entry.get("request", {}).get("url", "")
        method = entry.get("request", {}).get("method", "GET")
        status = entry.get("response", {}).get("status", 0)
        mime = entry.get("response", {}).get("content", {}).get("mimeType", "")

        requests.append({
            "url": url,
            "method": method,
            "status": status,
            "mime": mime,
            "duration_ms": round(duration_ms, 1),
            "started": started,
            "end_time": end_time,
        })

    overall_start = min(start_times)
    overall_end = max(end_times)
    total_ms = (overall_end - overall_start).total_seconds() * 1000

    return requests, round(total_ms, 1)


# ─────────────────────────────────────────────
# PARSE JMETER SUMMARY CSV
# ─────────────────────────────────────────────

def parse_jmeter_csv(csv_path):
    """
    JMeter Summary Report CSV columns:
    Label, # Samples, Average, Min, Max, Std. Dev., Error %, Throughput,
    Received KB/sec, Sent KB/sec, Avg. Bytes
    """
    samplers = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            label = row.get("Label", "").strip()
            if not label or label.lower() == "total":
                continue
            try:
                avg_ms = float(row.get("Average", 0))
                min_ms = float(row.get("Min", 0))
                max_ms = float(row.get("Max", 0))
                samples = int(row.get("# Samples", 0))
                error_pct = float(row.get("Error %", "0").replace("%", ""))
            except ValueError:
                continue

            samplers.append({
                "label": label,
                "avg_ms": round(avg_ms, 1),
                "min_ms": round(min_ms, 1),
                "max_ms": round(max_ms, 1),
                "samples": samples,
                "error_pct": round(error_pct, 2),
            })
    return samplers


# ─────────────────────────────────────────────
# URL MATCHING
# ─────────────────────────────────────────────

def normalize_url(url):
    """Extract path for matching — strip scheme, host, query params."""
    try:
        p = urlparse(url)
        return p.path.rstrip("/").lower()
    except Exception:
        return url.lower()


def strip_label_suffix(label):
    """
    Strip a trailing auto-generated numeric suffix from a JMeter sampler label,
    e.g. "/api/session-1" -> "/api/session", "/api/session_2" -> "/api/session",
    "/api/session (3)" -> "/api/session", "/api/session 4" -> "/api/session".

    JMeter appends suffixes like this when an element is duplicated/copy-pasted
    in the test plan. Requires at least one separator (space, "-", "_") before
    the digits, so genuine path segments like "/api/products/4521" (no separator
    before "4521" other than "/") are left untouched.
    """
    import re
    return re.sub(r'[\s_\-]+\(?\d+\)?\s*$', '', label).strip()


def match_requests(har_requests, jmeter_samplers):
    """
    Match HAR requests to JMeter samplers by URL path similarity.

    This is a many-to-one (HAR -> JMeter) matcher: a single JMeter sampler
    row represents the AGGREGATE of every sample with that label, so if a
    page calls the same endpoint multiple times (e.g. an initial search plus
    an AJAX refresh), every one of those HAR requests should match the SAME
    JMeter row — not just the first one.

    Returns list of matched pairs + unmatched from each side.
    """
    matched = []
    unmatched_har = []
    matched_sampler_indices = set()

    for hr in har_requests:
        har_path = normalize_url(hr["url"])
        best_match = None
        best_score = 0

        for i, js in enumerate(jmeter_samplers):
            # Try matching label against HAR URL path — both as-is, and with
            # a trailing auto-generated numeric suffix stripped (e.g. "-1", "_2", "(3)")
            label_candidates = [js["label"]]
            stripped = strip_label_suffix(js["label"])
            if stripped != js["label"]:
                label_candidates.append(stripped)

            for label in label_candidates:
                label_norm = label.lower().replace(" ", "/")
                jmeter_path = normalize_url(label) if "/" in label else label_norm

                # Score: exact path match > partial match > label in url > url in label
                # Guard empty strings: "/x".endswith("") and "" in "/x" are both
                # True in Python, which would make the HAR root path ("/" -> "")
                # spuriously match every JMeter sampler.
                if har_path == jmeter_path:
                    score = 100
                elif har_path and jmeter_path and (har_path.endswith(jmeter_path) or jmeter_path.endswith(har_path)):
                    score = 80
                elif har_path and jmeter_path and jmeter_path in har_path:
                    score = 60
                elif any(seg in har_path for seg in jmeter_path.split("/") if len(seg) > 3):
                    score = 40
                else:
                    score = 0

                if score > best_score:
                    best_score = score
                    best_match = (i, js, score)

        if best_match and best_score >= 40:
            idx, js, score = best_match
            matched_sampler_indices.add(idx)
            diff_ms = round(hr["duration_ms"] - js["avg_ms"], 1)
            diff_pct = round((diff_ms / js["avg_ms"] * 100), 1) if js["avg_ms"] > 0 else 0
            matched.append({
                "har": hr,
                "jmeter": js,
                "diff_ms": diff_ms,
                "diff_pct": diff_pct,
                "match_score": score,
            })
        else:
            unmatched_har.append(hr)

    unmatched_jmeter = [js for i, js in enumerate(jmeter_samplers) if i not in matched_sampler_indices]

    return matched, unmatched_har, unmatched_jmeter


# ─────────────────────────────────────────────
# SHORT URL
# ─────────────────────────────────────────────

def short_url(url, max_len=55):
    try:
        p = urlparse(url)
        s = p.path
        if len(s) > max_len:
            s = "…" + s[-max_len:]
        return s or url[:max_len]
    except Exception:
        return url[:max_len]


def diff_class(diff_ms):
    if diff_ms > 500:
        return "neg"
    elif diff_ms > 100:
        return "warn"
    elif diff_ms < -100:
        return "pos"
    return "neutral"


def diff_label(diff_ms):
    if diff_ms > 0:
        return f"+{diff_ms} ms (HAR slower)"
    elif diff_ms < 0:
        return f"{diff_ms} ms (JMeter slower)"
    return "0 ms (same)"


# ─────────────────────────────────────────────
# HTML REPORT
# ─────────────────────────────────────────────

def generate_report(har_path, csv_path, output_path):
    print(f"\nReading HAR  : {har_path}")
    print(f"Reading CSV  : {csv_path}")

    har_requests, har_total_ms = parse_har(har_path)
    jmeter_samplers = parse_jmeter_csv(csv_path)

    print(f"HAR requests : {len(har_requests)}  |  total: {har_total_ms}ms")
    print(f"JMeter rows  : {len(jmeter_samplers)}")

    matched, unmatched_har, unmatched_jmeter = match_requests(har_requests, jmeter_samplers)
    print(f"Matched      : {len(matched)}  |  unmatched HAR: {len(unmatched_har)}  |  unmatched JMeter: {len(unmatched_jmeter)}")

    generated_at = datetime.now().strftime("%d %b %Y, %H:%M")
    har_name = os.path.basename(har_path)
    csv_name = os.path.basename(csv_path)

    # Summary stats
    if matched:
        avg_diff = round(sum(m["diff_ms"] for m in matched) / len(matched), 1)
        max_diff_item = max(matched, key=lambda x: x["diff_ms"])
        total_har_matched = sum(m["har"]["duration_ms"] for m in matched)
        total_jmeter_matched = sum(m["jmeter"]["avg_ms"] for m in matched)
    else:
        avg_diff = 0
        max_diff_item = None
        total_har_matched = total_jmeter_matched = 0

    # Build matched rows
    matched_rows = ""
    for m in sorted(matched, key=lambda x: abs(x["diff_ms"]), reverse=True):
        hr = m["har"]
        js = m["jmeter"]
        dc = diff_class(m["diff_ms"])
        dl = diff_label(m["diff_ms"])
        bar_har = min((hr["duration_ms"] / max(hr["duration_ms"], js["avg_ms"])) * 100, 100)
        bar_jm = min((js["avg_ms"] / max(hr["duration_ms"], js["avg_ms"])) * 100, 100)
        su = short_url(hr["url"])
        score = m["match_score"]
        score_class = "score-strong" if score >= 100 else "score-medium" if score >= 80 else "score-weak"

        matched_rows += f"""
        <tr>
          <td class="url-cell">
            <div class="url-main" title="{hr['url']}">{su}</div>
            <div class="url-sub">↔ <span class="jmeter-label">{js['label']}</span> <span class="score-badge {score_class}">match {score}</span></div>
          </td>
          <td class="num">{hr['duration_ms']}</td>
          <td class="num">{js['avg_ms']}</td>
          <td class="diff {dc}">{dl}</td>
          <td class="bar-cell">
            <div class="bar-wrap">
              <div class="bar-row"><span class="bar-lbl">HAR</span><div class="bar-bg"><div class="bar-fill har-bar" style="width:{bar_har:.0f}%"></div></div></div>
              <div class="bar-row"><span class="bar-lbl">JMT</span><div class="bar-bg"><div class="bar-fill jmt-bar" style="width:{bar_jm:.0f}%"></div></div></div>
            </div>
          </td>
          <td class="num muted">{js['samples']}</td>
          <td class="num {'err' if js['error_pct'] > 0 else 'muted'}">{js['error_pct']}%</td>
        </tr>"""

    # Unmatched HAR rows
    unmatched_har_rows = ""
    for hr in unmatched_har[:20]:
        unmatched_har_rows += f"""
        <tr>
          <td class="url-cell" title="{hr['url']}">{short_url(hr['url'])}</td>
          <td class="num">{hr['duration_ms']} ms</td>
          <td class="muted" colspan="2">No JMeter match found</td>
        </tr>"""

    # Unmatched JMeter rows
    unmatched_jmeter_rows = ""
    for js in unmatched_jmeter:
        unmatched_jmeter_rows += f"""
        <tr>
          <td class="url-cell">{js['label']}</td>
          <td class="num">{js['avg_ms']} ms</td>
          <td class="muted" colspan="2">No HAR match found</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HAR vs JMeter — Comparison Report</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0E1117;color:#C9D1D9;font-size:13px}}

  .topbar{{background:#161B22;border-bottom:1px solid #21262D;padding:14px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}}
  .topbar-title{{font-size:15px;font-weight:600;color:#E6EDF3}}
  .topbar-sub{{font-size:12px;color:#6E7681;margin-top:2px}}
  .topbar-meta{{font-size:12px;color:#6E7681;text-align:right}}

  .stats{{display:grid;grid-template-columns:repeat(5,1fr);border-bottom:1px solid #21262D}}
  .stat{{padding:18px 24px;border-right:1px solid #21262D}}
  .stat:last-child{{border-right:none}}
  .stat-val{{font-size:24px;font-weight:600;letter-spacing:-0.5px;color:#E6EDF3;font-variant-numeric:tabular-nums}}
  .stat-val.green{{color:#3FB950}}
  .stat-val.amber{{color:#D29922}}
  .stat-val.red{{color:#F85149}}
  .stat-val.blue{{color:#58A6FF}}
  .stat-label{{font-size:11px;color:#6E7681;margin-top:3px;text-transform:uppercase;letter-spacing:0.8px}}

  .section{{padding:20px 28px;border-bottom:1px solid #21262D}}
  .section-title{{font-size:12px;font-weight:600;color:#8B949E;text-transform:uppercase;letter-spacing:1px;margin-bottom:14px;display:flex;align-items:center;gap:8px}}
  .badge{{font-size:11px;padding:2px 8px;border-radius:10px;background:#21262D;color:#8B949E;font-weight:400}}

  .legend{{display:flex;gap:20px;margin-bottom:14px;flex-wrap:wrap}}
  .leg-item{{display:flex;align-items:center;gap:6px;font-size:12px;color:#8B949E}}
  .leg-dot{{width:12px;height:6px;border-radius:2px}}

  table{{width:100%;border-collapse:collapse}}
  th{{font-size:11px;font-weight:600;color:#6E7681;text-transform:uppercase;letter-spacing:0.8px;padding:7px 8px;border-bottom:1px solid #21262D;text-align:left;white-space:nowrap}}
  td{{padding:7px 8px;border-bottom:1px solid #161B22;vertical-align:middle}}
  tr:hover td{{background:#161B22}}

  .url-cell{{font-family:monospace;font-size:11px;color:#8B949E;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .url-main{{color:#C9D1D9;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .url-sub{{margin-top:3px;font-size:10px;color:#6E7681;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .jmeter-label{{color:#58A6FF}}
  .score-badge{{display:inline-block;font-size:9px;font-weight:600;padding:1px 5px;border-radius:3px;margin-left:4px}}
  .score-strong{{background:#1A4731;color:#3FB950}}
  .score-medium{{background:#2D2A1A;color:#D29922}}
  .score-weak{{background:#3D1A1A;color:#F85149}}
  .num{{font-family:monospace;font-size:12px;text-align:right;white-space:nowrap;color:#C9D1D9}}
  .muted{{color:#6E7681}}
  .err{{color:#F85149;font-weight:600}}

  .diff{{font-size:12px;font-weight:500;white-space:nowrap}}
  .diff.neg{{color:#F85149}}
  .diff.warn{{color:#D29922}}
  .diff.pos{{color:#3FB950}}
  .diff.neutral{{color:#6E7681}}

  .bar-cell{{width:160px;padding:4px 8px}}
  .bar-wrap{{display:flex;flex-direction:column;gap:3px}}
  .bar-row{{display:flex;align-items:center;gap:5px}}
  .bar-lbl{{font-size:10px;color:#6E7681;width:24px;flex-shrink:0}}
  .bar-bg{{flex:1;background:#21262D;border-radius:2px;height:6px;overflow:hidden}}
  .bar-fill{{height:100%;border-radius:2px}}
  .har-bar{{background:#58A6FF}}
  .jmt-bar{{background:#0F6E56}}

  .insight-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
  .insight-card{{background:#161B22;border:1px solid #21262D;border-radius:8px;padding:14px}}
  .insight-icon{{font-size:18px;margin-bottom:8px}}
  .insight-title{{font-size:13px;font-weight:500;color:#E6EDF3;margin-bottom:4px}}
  .insight-body{{font-size:12px;color:#8B949E;line-height:1.6}}

  .why-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
  .why-card{{background:#161B22;border:1px solid #21262D;border-radius:8px;padding:16px}}
  .why-card.why-har{{border-left:3px solid #58A6FF}}
  .why-card.why-jmeter{{border-left:3px solid #0F6E56}}
  .why-card-title{{font-size:13px;font-weight:600;color:#E6EDF3;margin-bottom:4px}}
  .why-card-sub{{font-size:11px;color:#6E7681;margin-bottom:10px;font-style:italic}}
  .why-list{{list-style:none;display:flex;flex-direction:column;gap:7px}}
  .why-list li{{font-size:12px;color:#8B949E;line-height:1.5;padding-left:16px;position:relative}}
  .why-list li::before{{content:"›";position:absolute;left:0;color:#6E7681;font-weight:700}}
  .why-list li strong{{color:#C9D1D9;font-weight:500}}
  .why-tagline{{margin-top:12px;padding-top:10px;border-top:1px solid #21262D;font-size:12px;color:#8B949E;font-style:italic}}

  .footer{{padding:14px 28px;font-size:11px;color:#6E7681;border-top:1px solid #21262D;display:flex;justify-content:space-between}}
  .footer span{{color:#0F6E56;font-weight:500}}

  @media(max-width:700px){{
    .stats{{grid-template-columns:1fr 1fr}}
    .stat{{border-right:none;border-bottom:1px solid #21262D}}
    .bar-cell{{display:none}}
    .insight-grid{{grid-template-columns:1fr}}
    .why-grid{{grid-template-columns:1fr}}
  }}
</style>
</head>
<body>

<div class="topbar">
  <div>
    <div class="topbar-title">HAR vs JMeter — Side-by-side Comparison</div>
    <div class="topbar-sub">{har_name} &nbsp;⟷&nbsp; {csv_name}</div>
  </div>
  <div class="topbar-meta">Generated {generated_at}<br>by Visvashwarr Venugopal</div>
</div>

<div class="stats">
  <div class="stat">
    <div class="stat-val blue">{har_total_ms} ms</div>
    <div class="stat-label">HAR total load time</div>
  </div>
  <div class="stat">
    <div class="stat-val">{len(har_requests)}</div>
    <div class="stat-label">HAR requests</div>
  </div>
  <div class="stat">
    <div class="stat-val">{len(jmeter_samplers)}</div>
    <div class="stat-label">JMeter samplers</div>
  </div>
  <div class="stat">
    <div class="stat-val {'green' if avg_diff <= 0 else 'amber' if avg_diff < 200 else 'red'}">{'+' if avg_diff > 0 else ''}{avg_diff} ms</div>
    <div class="stat-label">Avg HAR vs JMeter diff</div>
  </div>
  <div class="stat">
    <div class="stat-val">{len(matched)}</div>
    <div class="stat-label">Matched requests</div>
  </div>
</div>

<div class="section">
  <div class="section-title">Key Insights</div>
  <div class="insight-grid">
    <div class="insight-card">
      <div class="insight-icon">⏱</div>
      <div class="insight-title">Wall-clock vs sampler time</div>
      <div class="insight-body">HAR captures true parallel browser load time. JMeter measures individual sampler response time. The gap = browser overhead + parallelism difference.</div>
    </div>
    <div class="insight-card">
      <div class="insight-icon">{'🔴' if avg_diff > 200 else '🟡' if avg_diff > 50 else '🟢'}</div>
      <div class="insight-title">Average difference: {'+' if avg_diff > 0 else ''}{avg_diff} ms</div>
      <div class="insight-body">{'HAR is consistently slower — browser overhead (DNS, SSL, render) is real and not captured in JMeter.' if avg_diff > 100 else 'HAR and JMeter are closely aligned — your JMeter script is a good representation of real browser behaviour.' if abs(avg_diff) < 50 else 'Minor gap detected — review individual request differences below.'}</div>
    </div>
    <div class="insight-card">
      <div class="insight-icon">🎯</div>
      <div class="insight-title">Matched {len(matched)} of {len(har_requests)} HAR requests</div>
      <div class="insight-body">{len(unmatched_har)} HAR requests had no JMeter equivalent — these may be 3rd party, browser-initiated, or not scripted. {len(unmatched_jmeter)} JMeter samplers had no HAR match.</div>
    </div>
  </div>
</div>

<div class="section">
  <div class="section-title">
    Request-level comparison
    <span class="badge">{len(matched)} matched · sorted by diff</span>
  </div>
  <div class="legend">
    <div class="leg-item"><div class="leg-dot" style="background:#58A6FF"></div>HAR time</div>
    <div class="leg-item"><div class="leg-dot" style="background:#0F6E56"></div>JMeter avg</div>
  </div>
  <table>
    <thead>
      <tr>
        <th>URL / Sampler</th>
        <th style="text-align:right">HAR (ms)</th>
        <th style="text-align:right">JMeter avg (ms)</th>
        <th>Difference</th>
        <th>Visual</th>
        <th style="text-align:right">Samples</th>
        <th style="text-align:right">Error %</th>
      </tr>
    </thead>
    <tbody>{matched_rows}</tbody>
  </table>
</div>

<div class="section">
  <div class="section-title">Why the diff? <span class="badge">reference guide</span></div>
  <div class="why-grid">
    <div class="why-card why-har">
      <div class="why-card-title">🌐 HAR &gt; JMeter</div>
      <div class="why-card-sub">The browser pays a tax JMeter doesn't</div>
      <ul class="why-list">
        <li><strong>DNS + SSL/TLS handshake</strong> — full connection setup cost, vs JMeter's keep-alive connection reuse</li>
        <li><strong>Render-blocking dependencies</strong> — the browser must parse HTML/CSS/JS before it even knows to fire the request</li>
        <li><strong>Per-host connection limits (~6)</strong> — the browser queues requests; JMeter threads aren't bound this way</li>
        <li><strong>Client-side JS execution</strong> — time spent running JS before the API call is triggered, invisible to JMeter</li>
        <li><strong>Real network conditions</strong> — latency and packet loss on the user's actual connection vs JMeter running from a datacenter</li>
        <li><strong>Cookie / auth overhead</strong> — full browser session sends more headers and cookies than a lean script</li>
      </ul>
      <div class="why-tagline">"The browser pays a tax JMeter doesn't — connection setup, rendering, real network."</div>
    </div>
    <div class="why-card why-jmeter">
      <div class="why-card-title">⚙️ JMeter &gt; HAR</div>
      <div class="why-card-sub">The backend pays a tax HAR doesn't</div>
      <ul class="why-list">
        <li><strong>Concurrent load</strong> — many virtual users hammering the backend simultaneously, vs HAR's single-user session</li>
        <li><strong>DB connection pool exhaustion</strong> — requests queue for a database connection under concurrency</li>
        <li><strong>Lock contention / row locking</strong> — concurrent writes cause DB locks a solo user never triggers</li>
        <li><strong>Cold vs warm caches</strong> — many threads with varied data may miss server-side caches a single session would hit</li>
        <li><strong>GC pauses / CPU saturation</strong> — JVM garbage collection or CPU maxing out under load adds latency</li>
        <li><strong>Insufficient think time</strong> — back-to-back requests with no pacing create artificial load spikes</li>
      </ul>
      <div class="why-tagline">"The backend pays a tax HAR doesn't — concurrency, contention, load."</div>
    </div>
  </div>
</div>

{'<div class="section"><div class="section-title">Unmatched HAR requests <span class="badge">not in JMeter script</span></div><table><thead><tr><th>URL</th><th style="text-align:right">HAR time</th><th colspan="2">Note</th></tr></thead><tbody>' + unmatched_har_rows + '</tbody></table></div>' if unmatched_har_rows else ''}

{'<div class="section"><div class="section-title">Unmatched JMeter samplers <span class="badge">not found in HAR</span></div><table><thead><tr><th>Sampler label</th><th style="text-align:right">Avg time</th><th colspan="2">Note</th></tr></thead><tbody>' + unmatched_jmeter_rows + '</tbody></table></div>' if unmatched_jmeter_rows else ''}

<div class="footer">
  <span>HAR Analyser</span> &nbsp;·&nbsp; by Visvashwarr Venugopal · Performance Engineer
  <span>{len(matched)} matched requests · {len(unmatched_har)} unmatched HAR · {len(unmatched_jmeter)} unmatched JMeter</span>
</div>

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nReport saved : {output_path}")
    return output_path


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# CLI ENTRY POINT (called by JMeter plugin)
# Usage: python har_vs_jmeter_core.py <har_file> <csv_file> <output_html>
# ─────────────────────────────────────────────
import sys as _sys
if __name__ == "__main__":
    if len(_sys.argv) == 4:
        generate_report(_sys.argv[1], _sys.argv[2], _sys.argv[3])
    else:
        print("Usage: python har_vs_jmeter_core.py <har_file> <jmeter_summary_csv> <output_html>")
        _sys.exit(1)

