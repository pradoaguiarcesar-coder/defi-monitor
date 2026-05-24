"""
Configuração do DeFi Monitor.

Lista de protocolos monitorados + thresholds para alertas.
Edite este arquivo para adicionar/remover protocolos ou ajustar sensibilidade.
"""

# ============================================================
# PROTOCOLOS MONITORADOS
# ============================================================
# Campos:
#   name: nome de exibição
#   token: ticker do token principal
#   defillama_slug: slug em api.llama.fi/protocol/{slug} (None se não listado)
#   coingecko_id: id em coingecko.com/api (None se não listado)
#   is_stablecoin: True se deve monitorar peg em $1
#   news_query: termos extras de busca para notícias (além do nome)

PROTOCOLS = [
    {
        "name": "OnRe",
        "token": "ONyc",
        "defillama_slug": "onre",
        "coingecko_id": None,           # ONyc não tem ID no CoinGecko ainda
        "is_stablecoin": False,         # ONyc é yield-bearing, NÃO mantém peg em $1
        "news_query": "OnRe ONyc reinsurance",
    },
    {
        "name": "Altura",
        "token": "AVLT",
        "defillama_slug": "altura",
        "coingecko_id": "altura-defi-ltd",
        "is_stablecoin": False,
        "news_query": "Altura AVLT DeFi",
    },
    {
        "name": "Unitas",
        "token": "USDu",
        "defillama_slug": "unitas",
        "coingecko_id": None,
        "is_stablecoin": True,
        "news_query": "Unitas USDu stablecoin",
    },
    {
        "name": "Hylo",
        "token": "hyUSD",
        "defillama_slug": "hylo",
        "coingecko_id": None,
        "is_stablecoin": True,
        "news_query": "Hylo hyUSD Solana stablecoin",
    },
    {
        "name": "Paxos Global Dollar",
        "token": "USDG",
        "defillama_slug": None,         # USDG é stablecoin pura, não tem página de "protocol"
        "coingecko_id": "global-dollar",
        "is_stablecoin": True,
        "news_query": "USDG Paxos Global Dollar",
    },
    {
        "name": "Ethena",
        "token": "USDe",
        "defillama_slug": "ethena",
        "coingecko_id": "ethena-usde",
        "is_stablecoin": True,
        "news_query": "Ethena USDe synthetic dollar",
    },
    {
        "name": "Apyx",
        "token": "apxUSD/apyUSD",
        "defillama_slug": "apyx",       # Protocolo novo, slug pode ainda não existir
        "coingecko_id": None,
        "is_stablecoin": True,
        "news_query": "Apyx apxUSD apyUSD stablecoin",
    },
]


# ============================================================
# THRESHOLDS DE ALERTA
# ============================================================
# Valores em porcentagem. Ajuste conforme sua tolerância a risco.

THRESHOLDS = {
    # Queda de TVL em 24h
    "tvl_change_24h_alert": -10.0,   # 🔴 vermelho se queda > 10% em 1 dia
    "tvl_change_24h_warn":  -5.0,    # 🟡 amarelo se queda > 5%

    # Queda de TVL em 7 dias
    "tvl_change_7d_warn":   -15.0,   # 🟡 se queda > 15% na semana

    # Desvio de peg para stablecoins (% em relação a $1)
    "peg_deviation_alert":  1.0,     # 🔴 desvio > 1% (ex: $0.99 ou $1.01)
    "peg_deviation_warn":   0.3,     # 🟡 desvio > 0.3%
}


# ============================================================
# PALAVRAS-CHAVE DE RISCO EM NOTÍCIAS
# ============================================================
# Termos buscados nas notícias coletadas (case-insensitive).
# CRÍTICAS marcam o protocolo como 🔴.
# ATENÇÃO marcam como 🟡 (se nada pior).

RISK_KEYWORDS_CRITICAL = [
    # Inglês
    "hack", "hacked", "exploit", "exploited", "drained", "drain",
    "rug", "rugpull", "rug pull", "paused", "halted", "frozen",
    "depeg", "depegged", "vulnerability", "compromised",
    "stolen", "lost funds", "emergency",
    # Português
    "hackeado", "hackeada", "explorado", "explorada", "drenado",
    "congelado", "perdeu fundos", "vulnerabilidade",
    "emergência", "pausado",
]

RISK_KEYWORDS_WARNING = [
    # Inglês
    "investigation", "investigated", "concern", "warning",
    "lawsuit", "regulatory action", "sanctioned", "sec ",
    "delisted", "delisting", "scrutiny", "probe",
    # Português
    "investigação", "preocupação", "ação regulatória",
    "sancionado", "deslistado", "alerta",
]


# ============================================================
# CONFIGURAÇÃO DE NOTÍCIAS
# ============================================================
# Janela de busca (horas) — notícias mais antigas são ignoradas.
NEWS_LOOKBACK_HOURS = 24

# Máximo de notícias por protocolo na busca.
NEWS_MAX_PER_PROTOCOL = 8
