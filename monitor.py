#!/usr/bin/env python3
"""DeFi Monitor v2 — Agente de monitoramento de protocolos DeFi."""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from config import (
    GRANULAR_MARKETS,
    HACKS_LOOKBACK_HOURS,
    MARKET_WIDE_NEWS_QUERIES,
    NEWS_LOOKBACK_HOURS,
    NEWS_MAX_PER_PROTOCOL,
    PROTOCOLS,
    RISK_KEYWORDS_CRITICAL,
    RISK_KEYWORDS_WARNING,
    THRESHOLDS,
)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
SNAPSHOTS_FILE = "snapshots.json"
HTTP_TIMEOUT = 25
USER_AGENT = "defi-monitor/2.0 (+https://github.com)"
BR_TZ = timezone(timedelta(hours=-3))


def _http_get(url, accept="application/json"):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"  ! HTTP {e.code} em {url}", file=sys.stderr)
    except Exception as e:
        print(f"  ! Erro em {url}: {e}", file=sys.stderr)
    return None


def http_get_json(url):
    body = _http_get(url, accept="application/json")
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def http_get_xml(url):
    body = _http_get(url, accept="application/rss+xml")
    if not body:
        return None
    try:
        return ET.fromstring(body)
    except ET.ParseError:
        return None


_pools_cache = None


def get_defillama_pools():
    global _pools_cache
    if _pools_cache is not None:
        return _pools_cache
    print("  · Baixando pools do DefiLlama...")
    data = http_get_json("https://yields.llama.fi/pools")
    if data and isinstance(data, dict) and "data" in data:
        _pools_cache = data["data"]
    else:
        _pools_cache = []
    print(f"  · {len(_pools_cache)} pools carregados.")
    return _pools_cache


def fetch_defillama(slug):
    if not slug:
        return None
    data = http_get_json(f"https://api.llama.fi/protocol/{slug}")
    if not data:
        return None
    chains = data.get("currentChainTvls", {}) or {}
    tvl_now = sum(
        v for k, v in chains.items()
        if isinstance(v, (int, float))
        and not any(k.endswith(s) for s in ("-borrowed", "-pool2", "-staking", "-vesting"))
    )
    tvl_series = data.get("tvl") or []
    change_1d = _pct_change_from_series(tvl_series, hours=24)
    change_7d = _pct_change_from_series(tvl_series, hours=24 * 7)
    return {"tvl": tvl_now if tvl_now > 0 else None, "change_1d": change_1d, "change_7d": change_7d}


def _pct_change_from_series(series, hours):
    if not series or len(series) < 2:
        return None
    last = series[-1]
    last_ts = last.get("date")
    last_val = last.get("totalLiquidityUSD") or last.get("tvl")
    if not last_ts or not last_val:
        return None
    target_ts = last_ts - (hours * 3600)
    prev = None
    for point in reversed(series):
        if point.get("date", 0) <= target_ts:
            prev = point
            break
    if not prev:
        prev = series[0]
    prev_val = prev.get("totalLiquidityUSD") or prev.get("tvl")
    if not prev_val:
        return None
    return ((last_val - prev_val) / prev_val) * 100.0


def fetch_defi_hacks():
    data = http_get_json("https://api.llama.fi/hacks")
    if not data or not isinstance(data, list):
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=HACKS_LOOKBACK_HOURS)).timestamp()
    recent = []
    for hack in data:
        ts = hack.get("date")
        if not ts:
            continue
        if ts >= cutoff:
            chain = hack.get("chain")
            if isinstance(chain, list):
                chain = ", ".join(chain)
            recent.append({
                "name": hack.get("name", "?"),
                "amount": hack.get("amount"),
                "chain": chain,
                "date": ts,
                "source": hack.get("source"),
                "technique": hack.get("technique") or hack.get("techniqe"),
            })
    return sorted(recent, key=lambda h: h["date"], reverse=True)


def fetch_coingecko_price(coin_id):
    if not coin_id:
        return None
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
    data = http_get_json(url)
    if not data or coin_id not in data:
        return None
    info = data[coin_id]
    return {"price": info.get("usd"), "change_24h": info.get("usd_24h_change")}


def fetch_eth_price():
    data = http_get_json("https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd")
    if not data or "ethereum" not in data:
        return None
    return data["ethereum"].get("usd")


def fetch_news(query, max_items=None):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    root = http_get_xml(url)
    if root is None:
        return []
    limit = max_items or NEWS_MAX_PER_PROTOCOL
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_LOOKBACK_HOURS)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_str = (item.findtext("pubDate") or "").strip()
        pub_dt = None
        if pub_str:
            try:
                pub_dt = parsedate_to_datetime(pub_str)
            except (TypeError, ValueError):
                pass
        if pub_dt and pub_dt < cutoff:
            continue
        items.append({"title": title, "link": link, "published": pub_dt})
        if len(items) >= limit:
            break
    return items


def classify_news(news_items):
    critical, warning, neutral = [], [], []
    for item in news_items:
        title_lc = item["title"].lower()
        if any(re.search(rf"\b{re.escape(kw)}", title_lc) for kw in RISK_KEYWORDS_CRITICAL):
            critical.append(item)
        elif any(re.search(rf"\b{re.escape(kw)}", title_lc) for kw in RISK_KEYWORDS_WARNING):
            warning.append(item)
        else:
            neutral.append(item)
    return critical, warning, neutral


def fetch_market_wide_news():
    seen = set()
    critical_all = []
    for query in MARKET_WIDE_NEWS_QUERIES:
        news = fetch_news(query, max_items=10)
        critical, _, _ = classify_news(news)
        for item in critical:
            if item["title"] not in seen:
                seen.add(item["title"])
                critical_all.append(item)
        time.sleep(0.6)
    critical_all.sort(
        key=lambda x: x.get("published") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return critical_all[:6]


def fetch_market_pools(project, symbol_keywords):
    pools = get_defillama_pools()
    if not pools:
        return []
    filtered = []
    for p in pools:
        if p.get("project") != project:
            continue
        if symbol_keywords:
            sym = (p.get("symbol") or "").upper()
            if not any(kw.upper() in sym for kw in symbol_keywords):
                continue
        filtered.append(p)
    filtered.sort(key=lambda x: x.get("tvlUsd") or 0, reverse=True)
    return filtered


def assess_market_health(pool, prev_pool=None):
    flags = []
    status = "🟢"

    def degrade_to(new_status):
        nonlocal status
        order = {"🟢": 0, "🟡": 1, "🔴": 2}
        if order[new_status] > order[status]:
            status = new_status

    util = pool.get("utilization")
    if util is None:
        borrowed = pool.get("totalBorrowUsd")
        supply = pool.get("totalSupplyUsd") or pool.get("tvlUsd")
        if borrowed and supply and supply > 0:
            util = (borrowed / supply) * 100
    if util is not None:
        if util > THRESHOLDS["market_utilization_alert"]:
            degrade_to("🔴")
            flags.append(f"Utilização {util:.0f}% (stress)")
        elif util > THRESHOLDS["market_utilization_warn"]:
            degrade_to("🟡")
            flags.append(f"Utilização {util:.0f}%")

    apy_pct_1d = pool.get("apyPct1D")
    if apy_pct_1d is not None:
        if apy_pct_1d > THRESHOLDS["market_apy_spike_alert"]:
            degrade_to("🔴")
            flags.append(f"APY +{apy_pct_1d:.0f}% em 24h")
        elif apy_pct_1d > THRESHOLDS["market_apy_spike_warn"]:
            degrade_to("🟡")
            flags.append(f"APY +{apy_pct_1d:.0f}% em 24h")

    if prev_pool:
        curr_tvl = pool.get("tvlUsd")
        prev_tvl = prev_pool.get("tvlUsd")
        if curr_tvl and prev_tvl and prev_tvl > 0:
            delta = ((curr_tvl - prev_tvl) / prev_tvl) * 100
            if delta < THRESHOLDS["market_tvl_drop_1h_alert"]:
                degrade_to("🔴")
                flags.append(f"TVL caiu {delta:+.1f}% em 1h")
            elif delta < THRESHOLDS["market_tvl_drop_1h_warn"]:
                degrade_to("🟡")
                flags.append(f"TVL caiu {delta:+.1f}% em 1h")

    return status, flags


def load_snapshots():
    if not os.path.exists(SNAPSHOTS_FILE):
        return {}
    try:
        with open(SNAPSHOTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_snapshots(snap):
    with open(SNAPSHOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, ensure_ascii=False, default=str)


def assess_health(data):
    flags = []
    status = "🟢"

    def degrade_to(new_status):
        nonlocal status
        order = {"🟢": 0, "🟡": 1, "🔴": 2}
        if order[new_status] > order[status]:
            status = new_status

    c1 = data.get("change_1d")
    if c1 is not None:
        if c1 < THRESHOLDS["tvl_change_24h_alert"]:
            degrade_to("🔴")
            flags.append(f"TVL caiu {c1:+.1f}% em 24h")
        elif c1 < THRESHOLDS["tvl_change_24h_warn"]:
            degrade_to("🟡")
            flags.append(f"TVL caiu {c1:+.1f}% em 24h")

    c7 = data.get("change_7d")
    if c7 is not None and c7 < THRESHOLDS["tvl_change_7d_warn"]:
        degrade_to("🟡")
        flags.append(f"TVL caiu {c7:+.1f}% em 7d")

    peg_dev = data.get("peg_deviation_pct")
    if peg_dev is not None:
        abs_dev = abs(peg_dev)
        if abs_dev > THRESHOLDS["peg_deviation_alert"]:
            degrade_to("🔴")
            flags.append(f"Peg desviou {peg_dev:+.2f}% de $1")
        elif abs_dev > THRESHOLDS["peg_deviation_warn"]:
            degrade_to("🟡")
            flags.append(f"Peg desviou {peg_dev:+.2f}% de $1")

    if data.get("news_critical"):
        degrade_to("🔴")
        flags.append(f"{len(data['news_critical'])} notícia(s) crítica(s)")
    elif data.get("news_warning"):
        degrade_to("🟡")
        flags.append(f"{len(data['news_warning'])} notícia(s) de atenção")

    return status, flags


def _fmt_usd(value):
    if value is None:
        return "—"
    if value >= 1e9:
        return f"${value/1e9:.2f}B"
    if value >= 1e6:
        return f"${value/1e6:.2f}M"
    if value >= 1e3:
        return f"${value/1e3:.1f}K"
    return f"${value:.0f}"


def _fmt_pct(value):
    if value is None:
        return "—"
    return f"{value:+.2f}%"


def _md_escape(text):
    return re.sub(r"([_*`\[\]])", r"\\\1", str(text))


def format_protocol_section(results):
    lines = []
    for r in results:
        lines.append(f"{r['status']} *{_md_escape(r['name'])}*  ({_md_escape(r['token'])})")
        if r.get("tvl") is not None:
            tvl_line = f"  • TVL: {_fmt_usd(r['tvl'])}"
            if r.get("change_1d") is not None:
                tvl_line += f"  ({_fmt_pct(r['change_1d'])} 24h"
                if r.get("change_7d") is not None:
                    tvl_line += f", {_fmt_pct(r['change_7d'])} 7d"
                tvl_line += ")"
            lines.append(tvl_line)
        elif r.get("defillama_slug"):
            lines.append("  • TVL: dado não disponível")
        if r.get("is_stablecoin") and r.get("price") is not None:
            lines.append(f"  • Preço: ${r['price']:.4f}  (peg: {_fmt_pct(r.get('peg_deviation_pct'))})")
        elif r.get("price") is not None:
            lines.append(f"  • Preço: ${r['price']:.4f}  ({_fmt_pct(r.get('change_24h'))} 24h)")
        if r.get("wsteth_eth_ratio") is not None:
            lines.append(f"  • wstETH/ETH: {r['wsteth_eth_ratio']:.4f}")
        for flag in r.get("flags", []):
            lines.append(f"  ⚡ {_md_escape(flag)}")
        for news in r.get("news_critical", [])[:1]:
            title = news["title"][:120] + ("…" if len(news["title"]) > 120 else "")
            lines.append(f"  📰 _{_md_escape(title)}_")
        lines.append("")
    return "\n".join(lines)


def format_granular_section(granular_results):
    if not granular_results:
        return ""
    lines = ["━━━━━━━━━━━━━━━", "📈 *Mercados granulares*", ""]
    for group in granular_results:
        lines.append(f"*{_md_escape(group['name'])}*")
        if group.get("aggregate_stats"):
            agg = group["aggregate_stats"]
            lines.append(
                f"  📊 Supply: {_fmt_usd(agg.get('total_supply'))}  "
                f"Borrow: {_fmt_usd(agg.get('total_borrow'))}  "
                f"Util média: {agg.get('avg_util', 0):.0f}%"
            )
        pools = group.get("pools", [])
        if not pools:
            lines.append("  _Sem mercados encontrados._")
            lines.append("")
            continue
        for p in pools:
            sym = _md_escape((p.get("symbol") or "?")[:40])
            tvl = _fmt_usd(p.get("tvlUsd"))
            apy = p.get("apy")
            apy_str = f"{apy:.1f}%" if apy is not None else "—"
            util = p.get("utilization")
            util_str = f"{util:.0f}%" if util is not None else "—"
            status = p.get("_status", "🟢")
            lines.append(f"  {status} {sym}: TVL {tvl}  util {util_str}  APY {apy_str}")
            for flag in p.get("_flags", []):
                lines.append(f"      ⚡ {_md_escape(flag)}")
        lines.append("")
    return "\n".join(lines)


def format_market_section(hacks, general_news):
    if not hacks and not general_news:
        return ""
    lines = ["━━━━━━━━━━━━━━━", "🌐 *Mercado DeFi*", ""]
    if hacks:
        lines.append(f"*Hacks recentes (últimas {HACKS_LOOKBACK_HOURS}h):*")
        for h in hacks[:4]:
            amt_str = _fmt_usd(h.get("amount")) if h.get("amount") else "?"
            tech = h.get("technique") or "?"
            chain = h.get("chain") or "?"
            lines.append(f"  🔴 {_md_escape(h['name'])} — {amt_str} ({chain}, {_md_escape(tech)})")
        lines.append("")
    if general_news:
        lines.append("*Notícias de risco em DeFi:*")
        for n in general_news[:4]:
            title = n["title"][:130] + ("…" if len(n["title"]) > 130 else "")
            lines.append(f"  ⚠️ _{_md_escape(title)}_")
        lines.append("")
    return "\n".join(lines)


def format_report(protocol_results, granular_results, hacks, general_news, now_br):
    red    = sum(1 for r in protocol_results if r["status"] == "🔴")
    yellow = sum(1 for r in protocol_results if r["status"] == "🟡")
    green  = sum(1 for r in protocol_results if r["status"] == "🟢")
    granular_red    = sum(1 for g in granular_results for p in g.get("pools", []) if p.get("_status") == "🔴")
    granular_yellow = sum(1 for g in granular_results for p in g.get("pools", []) if p.get("_status") == "🟡")

    lines = [
        "📊 *Relatório DeFi Monitor*",
        f"_{now_br.strftime('%d/%m/%Y %H:%M')} BRT_",
        "",
        f"*Protocolos:* 🟢 {green}   🟡 {yellow}   🔴 {red}",
    ]
    if granular_red + granular_yellow > 0:
        lines.append(f"*Mercados:* 🟡 {granular_yellow}   🔴 {granular_red}")
    if hacks:
        lines.append(f"*⚠️ {len(hacks)} hack(s) recentes no mercado*")
    lines.append("")
    lines.append(format_protocol_section(protocol_results))
    lines.append(format_granular_section(granular_results))
    lines.append(format_market_section(hacks, general_news))
    lines.append("━━━━━━━━━━━━━━━")
    if red > 0 or granular_red > 0:
        total = red + granular_red
        lines.append(f"🔴 *Ação sugerida:* reavaliar exposição em {total} ponto(s) com sinal crítico.")
    elif yellow > 0 or granular_yellow > 0:
        total = yellow + granular_yellow
        lines.append(f"🟡 *Monitorar:* {total} ponto(s) com sinal de atenção.")
    else:
        lines.append("🟢 *Tudo OK:* nenhum sinal de alerta nesta janela.")
    lines.append("")
    lines.append("_Análise automática baseada em regras. Não é recomendação de investimento — a decisão é sua._")
    return "\n".join(lines)


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ! TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurados.", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunks = _split_message(message, max_len=4000)
    ok = True
    for chunk in chunks:
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                if resp.status >= 300:
                    ok = False
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                err_body = str(e)
            print(f"  ! Telegram HTTP {e.code}: {err_body}", file=sys.stderr)
            ok = False
        except Exception as e:
            print(f"  ! Falha enviando ao Telegram: {e}", file=sys.stderr)
            ok = False
        time.sleep(0.4)
    return ok


def _split_message(text, max_len=4000):
    if len(text) <= max_len:
        return [text]
    chunks, current = [], []
    size = 0
    for line in text.split("\n"):
        if size + len(line) + 1 > max_len and current:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def process_protocol(proto, eth_price):
    print(f"\n→ {proto['name']} ({proto['token']})")
    result = {
        "name": proto["name"], "token": proto["token"],
        "defillama_slug": proto.get("defillama_slug"),
        "is_stablecoin": proto.get("is_stablecoin", False),
        "tvl": None, "change_1d": None, "change_7d": None,
        "price": None, "change_24h": None, "peg_deviation_pct": None,
        "wsteth_eth_ratio": None,
        "news_critical": [], "news_warning": [],
    }
    if proto.get("defillama_slug"):
        dl = fetch_defillama(proto["defillama_slug"])
        if dl:
            result["tvl"] = dl.get("tvl")
            result["change_1d"] = dl.get("change_1d")
            result["change_7d"] = dl.get("change_7d")
            print(f"  · TVL: {_fmt_usd(result['tvl'])}  24h: {_fmt_pct(result['change_1d'])}")
        else:
            print(f"  · DefiLlama: slug '{proto['defillama_slug']}' não encontrado")
        time.sleep(0.4)
    if proto.get("coingecko_id"):
        cg = fetch_coingecko_price(proto["coingecko_id"])
        if cg:
            result["price"] = cg.get("price")
            result["change_24h"] = cg.get("change_24h")
            if proto.get("is_stablecoin") and cg.get("price"):
                result["peg_deviation_pct"] = (cg["price"] - 1.0) * 100.0
            if proto.get("track_eth_ratio") and cg.get("price") and eth_price:
                result["wsteth_eth_ratio"] = cg["price"] / eth_price
        time.sleep(1.2)
    news = fetch_news(proto.get("news_query") or proto["name"])
    if news:
        critical, warning, _ = classify_news(news)
        result["news_critical"] = critical
        result["news_warning"] = warning
        print(f"  · Notícias: {len(news)} ({len(critical)} crítica, {len(warning)} atenção)")
    time.sleep(0.5)
    status, flags = assess_health(result)
    result["status"] = status
    result["flags"] = flags
    print(f"  → {status}")
    return result


def process_granular_market(spec, prev_snapshot):
    print(f"\n→ Granular: {spec['name']}")
    pools = fetch_market_pools(spec["defillama_project"], spec.get("symbol_keywords"))
    max_show = spec.get("max_show", 5)
    pools_top = pools[:max_show]
    prev_pools_dict = (prev_snapshot.get("granular", {}).get(spec["name"], {}) or {}).get("pools", {})
    for p in pools_top:
        pool_id = p.get("pool")
        prev_p = prev_pools_dict.get(pool_id) if pool_id else None
        status, flags = assess_market_health(p, prev_p)
        p["_status"] = status
        p["_flags"] = flags
    result = {"name": spec["name"], "pools": pools_top}
    if spec.get("aggregate") and pools:
        total_tvl = sum(p.get("tvlUsd") or 0 for p in pools)
        utils = [p.get("utilization") for p in pools if p.get("utilization") is not None]
        avg_util = sum(utils) / len(utils) if utils else 0
        total_borrow = sum(
            (p.get("tvlUsd") or 0) * ((p.get("utilization") or 0) / 100)
            for p in pools
        )
        result["aggregate_stats"] = {
            "total_supply": total_tvl,
            "total_borrow": total_borrow if total_borrow > 0 else None,
            "avg_util": avg_util,
        }
    print(f"  → {len(pools_top)} mercado(s)")
    return result


def main():
    now_utc = datetime.now(timezone.utc)
    now_br = now_utc.astimezone(BR_TZ)
    print(f"=== DeFi Monitor v2 — {now_br.strftime('%d/%m/%Y %H:%M')} BRT ===")
    snapshots = load_snapshots()
    eth_price = fetch_eth_price()
    if eth_price:
        print(f"ETH: ${eth_price:.2f}")
    time.sleep(0.8)
    print("\n--- PROTOCOLOS ---")
    protocol_results = [process_protocol(p, eth_price) for p in PROTOCOLS]
    print("\n--- GRANULARIDADE ---")
    granular_results = [process_granular_market(spec, snapshots) for spec in GRANULAR_MARKETS]
    print("\n--- MERCADO DEFI ---")
    print("Buscando hacks recentes...")
    hacks = fetch_defi_hacks()
    print(f"  {len(hacks)} hack(s) nas últimas {HACKS_LOOKBACK_HOURS}h")
    print("Buscando notícias gerais...")
    general_news = fetch_market_wide_news()
    print(f"  {len(general_news)} notícia(s)")
    report = format_report(protocol_results, granular_results, hacks, general_news, now_br)
    print("\n--- REPORT ---")
    print(report)
    print("--------------\n")
    sent = send_telegram(report)
    print(f"Telegram: {'✓ enviado' if sent else '✗ falha'}")
    new_snap = {
        "last_run": now_utc.isoformat(),
        "protocols": {
            r["name"]: {"tvl": r["tvl"], "price": r["price"], "status": r["status"]}
            for r in protocol_results
        },
        "granular": {
            g["name"]: {
                "pools": {
                    p.get("pool"): {"tvlUsd": p.get("tvlUsd"), "apy": p.get("apy")}
                    for p in g.get("pools", []) if p.get("pool")
                }
            }
            for g in granular_results
        },
    }
    save_snapshots(new_snap)
    print("Snapshot salvo.")


if __name__ == "__main__":
    main()
