#!/usr/bin/env python3
"""
DeFi Monitor — Agente de monitoramento de protocolos.

Coleta TVL, peg de stablecoins, fluxos relevantes e notícias dos protocolos
configurados em config.py, avalia risco com base em regras simples e envia
relatório consolidado via Telegram.

Roda 2x/dia via GitHub Actions (08:00 e 20:00 BRT).
Sem dependências externas — usa apenas Python stdlib.
"""

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
    NEWS_LOOKBACK_HOURS,
    NEWS_MAX_PER_PROTOCOL,
    PROTOCOLS,
    RISK_KEYWORDS_CRITICAL,
    RISK_KEYWORDS_WARNING,
    THRESHOLDS,
)

# =================== Configuração de runtime ===================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
SNAPSHOTS_FILE = "snapshots.json"
HTTP_TIMEOUT = 20
USER_AGENT = "defi-monitor/1.0 (+https://github.com)"

# Brasília é UTC-3 (Brasil não usa horário de verão desde 2019)
BR_TZ = timezone(timedelta(hours=-3))


# =================== Helpers HTTP ===================

def _http_get(url, accept="application/json"):
    """GET genérico. Retorna body em texto, ou None em erro."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": accept},
        )
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


# =================== Fonte: DefiLlama ===================

def fetch_defillama(slug):
    """
    Busca dados de TVL via endpoint /protocol/{slug}.
    Retorna dict com: tvl, change_1d, change_7d  (ou None se falhar).
    """
    if not slug:
        return None

    data = http_get_json(f"https://api.llama.fi/protocol/{slug}")
    if not data:
        return None

    # TVL atual = soma das chains (excluindo categorias derivadas)
    chains = data.get("currentChainTvls", {}) or {}
    tvl_now = sum(
        v for k, v in chains.items()
        if isinstance(v, (int, float))
        and not any(k.endswith(s) for s in ("-borrowed", "-pool2", "-staking", "-vesting"))
    )

    # Variações são calculadas a partir do histórico
    tvl_series = data.get("tvl") or []
    change_1d = _pct_change_from_series(tvl_series, hours=24)
    change_7d = _pct_change_from_series(tvl_series, hours=24 * 7)

    return {
        "tvl": tvl_now if tvl_now > 0 else None,
        "change_1d": change_1d,
        "change_7d": change_7d,
    }


def _pct_change_from_series(series, hours):
    """Calcula variação % entre ponto mais recente e ~N horas atrás."""
    if not series or len(series) < 2:
        return None

    last = series[-1]
    last_ts = last.get("date")
    last_val = last.get("totalLiquidityUSD") or last.get("tvl")
    if not last_ts or not last_val:
        return None

    target_ts = last_ts - (hours * 3600)
    # Encontra ponto mais próximo
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


# =================== Fonte: CoinGecko ===================

def fetch_coingecko_price(coin_id):
    """Busca preço atual + variação 24h. Retorna {price, change_24h} ou None."""
    if not coin_id:
        return None

    url = (
        f"https://api.coingecko.com/api/v3/simple/price"
        f"?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
    )
    data = http_get_json(url)
    if not data or coin_id not in data:
        return None

    info = data[coin_id]
    return {
        "price": info.get("usd"),
        "change_24h": info.get("usd_24h_change"),
    }


# =================== Fonte: Google News RSS ===================

def fetch_news(query):
    """Busca notícias recentes via Google News RSS."""
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    root = http_get_xml(url)
    if root is None:
        return []

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

        # Filtra notícias antigas
        if pub_dt and pub_dt < cutoff:
            continue

        items.append({"title": title, "link": link, "published": pub_dt})
        if len(items) >= NEWS_MAX_PER_PROTOCOL:
            break

    return items


def classify_news(news_items):
    """Separa notícias em críticas, atenção e neutras com base em palavras-chave."""
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


# =================== Snapshots ===================

def load_snapshots():
    """Carrega snapshots anteriores para comparação."""
    if not os.path.exists(SNAPSHOTS_FILE):
        return {}
    try:
        with open(SNAPSHOTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_snapshots(snap):
    """Persiste snapshot atual (commitado de volta no repo pelo GH Actions)."""
    with open(SNAPSHOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, ensure_ascii=False, default=str)


# =================== Avaliação de saúde ===================

def assess_health(data):
    """Aplica regras de threshold e retorna (status, lista_de_flags)."""
    flags = []
    status = "🟢"

    def degrade_to(new_status):
        nonlocal status
        order = {"🟢": 0, "🟡": 1, "🔴": 2}
        if order[new_status] > order[status]:
            status = new_status

    # Variação de TVL
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

    # Desvio de peg
    peg_dev = data.get("peg_deviation_pct")
    if peg_dev is not None:
        abs_dev = abs(peg_dev)
        if abs_dev > THRESHOLDS["peg_deviation_alert"]:
            degrade_to("🔴")
            flags.append(f"Peg desviou {peg_dev:+.2f}% de $1")
        elif abs_dev > THRESHOLDS["peg_deviation_warn"]:
            degrade_to("🟡")
            flags.append(f"Peg desviou {peg_dev:+.2f}% de $1")

    # Notícias
    if data.get("news_critical"):
        degrade_to("🔴")
        flags.append(f"{len(data['news_critical'])} notícia(s) com sinal crítico")
    elif data.get("news_warning"):
        degrade_to("🟡")
        flags.append(f"{len(data['news_warning'])} notícia(s) de atenção")

    return status, flags


# =================== Formatação do relatório ===================

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
    """Escapa caracteres especiais do Markdown legado do Telegram."""
    return re.sub(r"([_*`\[\]])", r"\\\1", str(text))


def format_report(results, now_br):
    """Monta a mensagem completa do relatório (markdown do Telegram)."""
    red = sum(1 for r in results if r["status"] == "🔴")
    yellow = sum(1 for r in results if r["status"] == "🟡")
    green = sum(1 for r in results if r["status"] == "🟢")

    lines = [
        "📊 *Relatório DeFi Monitor*",
        f"_{now_br.strftime('%d/%m/%Y %H:%M')} BRT_",
        "",
        f"*Resumo:* 🟢 {green}   🟡 {yellow}   🔴 {red}",
        "",
    ]

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
            lines.append("  • TVL: dado não disponível na DefiLlama")

        if r.get("is_stablecoin") and r.get("price") is not None:
            lines.append(f"  • Preço: ${r['price']:.4f}  (peg: {_fmt_pct(r.get('peg_deviation_pct'))})")
        elif r.get("price") is not None:
            lines.append(f"  • Preço: ${r['price']:.4f}  ({_fmt_pct(r.get('change_24h'))} 24h)")

        for flag in r.get("flags", []):
            lines.append(f"  ⚡ {_md_escape(flag)}")

        # Mostra título da notícia crítica mais recente (se houver)
        for news in r.get("news_critical", [])[:1]:
            title = news["title"][:120] + ("…" if len(news["title"]) > 120 else "")
            lines.append(f"  📰 _{_md_escape(title)}_")

        lines.append("")

    # Veredicto final
    lines.append("━━━━━━━━━━━━━━━")
    if red > 0:
        lines.append(f"🔴 *Ação sugerida:* reavaliar exposição em {red} protocolo(s) com sinal crítico.")
    elif yellow > 0:
        lines.append(f"🟡 *Monitorar:* {yellow} protocolo(s) com sinal de atenção. Acompanhar próxima janela.")
    else:
        lines.append("🟢 *Tudo OK:* nenhum sinal de alerta nesta janela.")

    lines.append("")
    lines.append(
        "_Análise automática baseada em regras (TVL, peg, notícias). "
        "Não é recomendação de investimento — a decisão é sua._"
    )

    return "\n".join(lines)


# =================== Telegram ===================

def send_telegram(message):
    """Envia mensagem via Bot API. Quebra em chunks se >4000 chars."""
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

        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                if resp.status >= 300:
                    ok = False
        except Exception as e:
            print(f"  ! Falha enviando ao Telegram: {e}", file=sys.stderr)
            ok = False
        time.sleep(0.3)

    return ok


def _split_message(text, max_len=4000):
    """Quebra texto preservando linhas inteiras."""
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


# =================== Orquestração principal ===================

def process_protocol(proto):
    """Processa um protocolo, retorna dict consolidado pra o relatório."""
    print(f"\n→ {proto['name']} ({proto['token']})")

    result = {
        "name": proto["name"],
        "token": proto["token"],
        "defillama_slug": proto.get("defillama_slug"),
        "is_stablecoin": proto.get("is_stablecoin", False),
        "tvl": None,
        "change_1d": None,
        "change_7d": None,
        "price": None,
        "change_24h": None,
        "peg_deviation_pct": None,
        "news_critical": [],
        "news_warning": [],
    }

    # DefiLlama (TVL)
    if proto.get("defillama_slug"):
        dl = fetch_defillama(proto["defillama_slug"])
        if dl:
            result["tvl"] = dl.get("tvl")
            result["change_1d"] = dl.get("change_1d")
            result["change_7d"] = dl.get("change_7d")
            print(f"  · TVL: {_fmt_usd(result['tvl'])}  24h: {_fmt_pct(result['change_1d'])}")
        else:
            print(f"  · DefiLlama: protocolo não encontrado (slug='{proto['defillama_slug']}')")
        time.sleep(0.4)

    # CoinGecko (preço/peg)
    if proto.get("coingecko_id"):
        cg = fetch_coingecko_price(proto["coingecko_id"])
        if cg:
            result["price"] = cg.get("price")
            result["change_24h"] = cg.get("change_24h")
            if proto.get("is_stablecoin") and cg.get("price"):
                result["peg_deviation_pct"] = (cg["price"] - 1.0) * 100.0
            print(f"  · Preço: ${cg.get('price')}")
        time.sleep(1.2)  # CoinGecko free tier: ~10 req/min

    # Notícias
    news = fetch_news(proto.get("news_query") or proto["name"])
    if news:
        critical, warning, _ = classify_news(news)
        result["news_critical"] = critical
        result["news_warning"] = warning
        print(f"  · Notícias: {len(news)} total, {len(critical)} crítica(s), {len(warning)} atenção")
    time.sleep(0.5)

    # Avaliação
    status, flags = assess_health(result)
    result["status"] = status
    result["flags"] = flags
    print(f"  → Status: {status}")

    return result


def main():
    now_utc = datetime.now(timezone.utc)
    now_br = now_utc.astimezone(BR_TZ)
    print(f"=== DeFi Monitor — {now_br.strftime('%d/%m/%Y %H:%M')} BRT ===")

    snapshots = load_snapshots()
    print(f"Snapshots anteriores: {len(snapshots.get('protocols', {}))}")

    results = [process_protocol(p) for p in PROTOCOLS]

    report = format_report(results, now_br)
    print("\n--- REPORT ---")
    print(report)
    print("--------------\n")

    sent = send_telegram(report)
    print(f"Telegram: {'✓ enviado' if sent else '✗ falha'}")

    # Salva snapshot pra próxima execução
    new_snap = {
        "last_run": now_utc.isoformat(),
        "protocols": {
            r["name"]: {
                "tvl": r["tvl"],
                "price": r["price"],
                "status": r["status"],
            }
            for r in results
        },
    }
    save_snapshots(new_snap)
    print(f"Snapshot salvo em {SNAPSHOTS_FILE}")


if __name__ == "__main__":
    main()
