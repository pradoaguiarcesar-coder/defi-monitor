# 📊 DeFi Monitor

Agente automático que monitora 7 protocolos DeFi 2x/dia (08:00 e 20:00 BRT)
e envia relatório consolidado pelo Telegram, com sinalização de risco.

**Custo:** R$ 0,00. Roda no plano gratuito do GitHub Actions.

---

## Protocolos monitorados

| Protocolo | Token | Tipo |
|-----------|-------|------|
| OnRe | ONyc | Reinsurance (Solana) |
| Altura | AVLT | Yield multi-estratégia (HyperEVM) |
| Unitas | USDu | Stablecoin yield (Solana) |
| Hylo | hyUSD | Stablecoin LST-backed (Solana) |
| Paxos Global Dollar | USDG | Stablecoin lastreada |
| Ethena | USDe | Dólar sintético delta-neutral |
| Apyx | apxUSD / apyUSD | Stablecoin dividend-backed |

## O que o relatório traz

Para cada protocolo:
- **TVL** atual e variação 24h / 7d
- **Peg** (para stablecoins) e desvio em relação a $1
- **Notícias recentes** das últimas 24h, com classificação automática
- **Status** visual: 🟢 saudável  🟡 atenção  🔴 sinal crítico
- **Veredicto geral** com sugestão de ação

### Regras de alerta

| Sinal | Critério |
|-------|----------|
| 🔴 Crítico | TVL caiu >10% em 24h **ou** peg desviou >1% **ou** notícia com palavras como "hack", "exploit", "depeg", "paused" |
| 🟡 Atenção | TVL caiu >5% em 24h ou >15% em 7d **ou** peg desviou >0,3% **ou** notícia com palavras como "investigation", "concern", "lawsuit" |
| 🟢 OK | Nada dos acima |

Os thresholds e palavras-chave estão em `config.py` e podem ser ajustados a qualquer momento.

---

## 🚀 Passo a passo de deploy

### Pré-requisitos

- Conta no GitHub (criar em [github.com](https://github.com) se ainda não tem — grátis)
- Bot do Telegram já criado (você já tem token e chat_id)

### Passo 1 — Criar o repositório

1. Acesse [github.com/new](https://github.com/new)
2. **Repository name:** `defi-monitor` (ou outro nome de sua preferência)
3. **Visibility:** marque **Private** (recomendado — assim só você vê)
4. Não marque "Add a README" — o nosso já está pronto
5. Clique em **Create repository**

### Passo 2 — Subir os arquivos

Pelo navegador, sem precisar instalar Git:

1. Na página do repo recém-criado, clique em **uploading an existing file** (link no meio da página)
2. Arraste todos os arquivos desta pasta (`config.py`, `monitor.py`, `snapshots.json`, `.gitignore`, `README.md`)
3. **Importante:** a pasta `.github/workflows/` precisa ir junto. No navegador você pode ter dificuldade com pastas — se for o caso, use a alternativa abaixo
4. Clique em **Commit changes**

**Alternativa — incluindo a pasta `.github/`:**

Se o navegador não aceitar a pasta oculta `.github/`, faça assim:

1. No repo, clique em **Add file → Create new file**
2. Em "Name your file", digite: `.github/workflows/monitor.yml` (o GitHub vai entender e criar as pastas)
3. Cole o conteúdo do arquivo `monitor.yml`
4. Clique em **Commit new file**

### Passo 3 — Adicionar os segredos

1. No repo, vá em **Settings** (aba no topo, à direita)
2. No menu lateral: **Secrets and variables → Actions**
3. Clique em **New repository secret**
4. Crie estes dois segredos:

   | Name | Value |
   |------|-------|
   | `TELEGRAM_BOT_TOKEN` | seu token do @BotFather |
   | `TELEGRAM_CHAT_ID` | seu chat_id do @userinfobot |

### Passo 4 — Testar manualmente

1. Vá na aba **Actions** do repo (no topo)
2. Se aparecer o aviso "Workflows aren't being run on this repository", clique em **I understand my workflows, go ahead and enable them**
3. No menu lateral, clique em **DeFi Monitor**
4. Clique em **Run workflow** (botão à direita) → **Run workflow**
5. Aguarde ~1–2 minutos. Quando a bolinha ficar verde ✅, vá ver no Telegram — o relatório deve ter chegado

### Passo 5 — Pronto

Daqui pra frente roda sozinho às **08:00 e 20:00 (horário de Brasília)** todos os dias.

> ⚠️ *Observação sobre horários:* o GitHub Actions roda crons em **best-effort** —
> em horários de pico do GitHub o agendamento pode atrasar de 5 a 30 minutos.
> Se isso for problema, dá pra programar 2 horários extras de "fallback".

---

## 🔒 Segurança — leia isto

**Importante:** você compartilhou seu token do bot na conversa onde este agente foi criado.
Para garantir que ninguém mais consiga controlar seu bot:

1. Abra o **@BotFather** no Telegram
2. Comando `/revoke`
3. Selecione seu bot
4. Ele invalida o token antigo e te dá um novo
5. Atualize o segredo `TELEGRAM_BOT_TOKEN` no GitHub (Settings → Secrets → editar)

Faça isso **depois** de confirmar que o primeiro relatório chegou no Telegram com o token antigo.

---

## 🛠️ Customizar

### Adicionar/remover protocolos

Edite `config.py`, ajuste a lista `PROTOCOLS` e commit. O próximo run já usa a nova lista.

Para descobrir o `defillama_slug` de um protocolo:
- Acesse `https://defillama.com/protocol/NOME-DO-PROTOCOLO`
- O slug é a parte final da URL

Para descobrir o `coingecko_id`:
- Acesse `https://www.coingecko.com/en/coins/NOME-DO-TOKEN`
- O id é a parte final da URL

### Ajustar sensibilidade dos alertas

Em `config.py`, edite `THRESHOLDS`. Valores mais negativos = menos sensível.

### Adicionar palavras-chave de risco

Em `config.py`, edite `RISK_KEYWORDS_CRITICAL` ou `RISK_KEYWORDS_WARNING`.

### Mudar horário dos relatórios

Edite `.github/workflows/monitor.yml`. As linhas com `cron:` usam **UTC**.
Brasília é UTC-3, então:
- 08:00 BRT = `0 11 * * *`
- 20:00 BRT = `0 23 * * *`
- 12:00 BRT = `0 15 * * *`

Use [crontab.guru](https://crontab.guru) para validar.

---

## 🐛 Troubleshooting

### "O relatório não chegou no Telegram"

1. Cheque os logs em **Actions → último run → "Rodar monitor"**
2. Procure por erros tipo `HTTP 401` (token errado) ou `chat not found` (chat_id errado)
3. Confirme que você iniciou conversa com seu bot pelo menos uma vez (mandou `/start`)

### "Workflow não roda automaticamente"

GitHub Actions desativa agendamentos em repos **sem commits há 60 dias**. Como o próprio agente
commita o snapshots.json a cada run, isso resolve sozinho. Mas se ficar parado, basta fazer um commit qualquer.

### "Algum protocolo aparece sem TVL"

Significa que esse slug ainda não está na DefiLlama (comum em protocolos muito novos como Apyx).
Para esses, o agente segue monitorando preço (CoinGecko) e notícias.
Tente atualizar o slug no `config.py` periodicamente.

### "Erro de Markdown ao enviar mensagem"

Pode acontecer se um título de notícia tiver caracteres especiais não escapados.
O código já trata os mais comuns (`_ * \` [ ]`). Se persistir, abra uma issue no repo
ou adicione mais caracteres ao `_md_escape()` em `monitor.py`.

---

## 📁 Estrutura

```
defi-monitor/
├── README.md                      ← este arquivo
├── monitor.py                     ← script principal
├── config.py                      ← lista de protocolos + thresholds
├── snapshots.json                 ← estado (auto-atualizado)
├── .gitignore
└── .github/
    └── workflows/
        └── monitor.yml            ← cron do GitHub Actions
```

---

## ⚖️ Disclaimer

Este agente fornece **análise automática baseada em regras** (TVL, peg, notícias).
**Não é recomendação de investimento.** As regras são heurísticas razoáveis, não
modelos preditivos. Você é o único responsável por decisões financeiras com base
no que ele reporta.

Em particular, lembre-se de que:
- "Sem alerta hoje" não significa "está seguro amanhã" — risco em DeFi pode aparecer rápido
- Notícias dependem do que está indexado no Google News; eventos em Discord/Twitter podem não aparecer
- TVL é um indicador entre vários — não captura tudo (especialmente risco de smart contract latente)

Use como **uma das fontes** da sua decisão, não a única.
