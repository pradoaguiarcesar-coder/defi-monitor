"""
Configuração do DeFi Monitor — v2.
"""

# ============================================================
# PROTOCOLOS MONITORADOS
# ============================================================

PROTOCOLS = [
    {
        "name": "OnRe",
        "token": "ONyc",
        "defillama_slug": "onre",
        "coingecko_id": None,
        "is_stablecoin": False,
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
        "defillama_slug": None,
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
        "defillama_slug": "apyx",
        "coingecko_id": None,
        "is_stablecoin": True,
        "news_query": "Apyx apxUSD apyUSD stablecoin",
    },
    {
        "name": "Lido (wstETH)",
        "token": "wstETH",
        "defillama_slug": "lido",
        "coingecko_id": "wrapped-steth",
        "is_stablecoin": False,
        "track_eth_ratio": True,
        "news_query": "Lido wstETH staked ETH",
    },
    {
        "name": "Exponent",
        "token": "Vault USDC",
        "defillama_slug": "exponent",
        "coingecko_id": None,
        "is_stablecoin": False,
        "news_query": "Exponent finance Solana yield",
    },
    {
        "name": "Morpho",
        "token": "Morpho Blue",
        "defillama_slug": "morpho-blue",
        "coingecko_id": "morpho",
        "is_stablecoin": False,
        "news_query": "Morpho Blue lending exploit",
    },
    {
        "name": "Project X",
        "token": "PRJX",
        "defillama_slug": "project-x",
        "coingecko_id": None,
        "is_stablecoin": False,
        "news_query": "Project X HyperEVM DEX",
    },
    {
        "name": "Kamino",
        "token": "K-Lend",
        "defillama_slug": "kamino-lend",
        "coingecko_id": "kamino",
        "is_stablecoin": False,
        "news_query": "Kamino lending Solana",
    },
]

GRANULAR_MARKETS = [
    {
        "name": "Morpho — mercados com WBTC",
        "defillama_project": "morpho-blue",
        "symbol_keywords": ["WBTC"],
        "max_show": 5,
    },
    {
        "name": "Morpho — mercados com wstETH",
        "defillama_project": "morpho-blue",
        "symbol_keywords": ["WSTETH", "WST-ETH"],
        "max_show": 5,
    },
    {
        "name": "Kamino — saúde dos empréstimos",
        "defillama_project": "kamino-lend",
        "symbol_keywords": None,
        "max_show": 8,
        "aggregate": True,
    },
]

THRESHOLDS = {
    "tvl_change_24h_alert":  -10.0,
    "tvl_change_24h_warn":   -5.0,
    "tvl_change_7d_warn":    -15.0,
    "peg_deviation_alert":   1.0,
    "peg_deviation_warn":    0.3,
    "market_utilization_alert": 95.0,
    "market_utilization_warn":  85.0,
    "market_apy_spike_alert":   100.0,
    "market_apy_spike_warn":    50.0,
    "market_tvl_drop_1h_alert": -15.0,
    "market_tvl_drop_1h_warn":  -8.0,
}

RISK_KEYWORDS_CRITICAL = [
    "hack", "hacked", "exploit", "exploited", "drained", "drain",
    "rug", "rugpull", "rug pull", "paused", "halted", "frozen",
    "depeg", "depegged", "vulnerability", "compromised",
    "stolen", "lost funds", "emergency", "attack", "attacked",
    "hackeado", "hackeada", "explorado", "explorada", "drenado",
    "congelado", "perdeu fundos", "vulnerabilidade",
    "emergência", "pausado", "ataque",
]

RISK_KEYWORDS_WARNING = [
    "investigation", "investigated", "concern", "warning",
    "lawsuit", "regulatory action", "sanctioned", "sec ",
    "delisted", "delisting", "scrutiny", "probe", "audit failed",
    "investigação", "preocupação", "ação regulatória",
    "sancionado", "deslistado", "alerta",
]

MARKET_WIDE_NEWS_QUERIES = [
    "DeFi hack exploit",
    "stablecoin depeg",
    "protocol drained smart contract",
    "DeFi vulnerability disclosure",
]

HACKS_LOOKBACK_HOURS = 72

NEWS_LOOKBACK_HOURS = 24
NEWS_MAX_PER_PROTOCOL = 6
