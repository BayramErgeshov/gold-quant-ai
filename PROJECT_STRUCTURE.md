# PROJECT_STRUCTURE.md

# GOLD QUANT AI

Version: 1.0

---

# PURPOSE

This document defines the complete project structure.

Claude must strictly follow this architecture.

Never create files outside this structure unless absolutely necessary.

Every folder has one responsibility.

Every module is isolated.

Every dependency is explicit.

---

# ROOT

```
gold-quant-ai/

├── README.md
├── LICENSE
├── CHANGELOG.md
├── CLAUDE.md
├── pyproject.toml
├── poetry.lock
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .gitignore
├── Makefile

├── docs/
├── config/
├── scripts/
├── data/
├── logs/
├── backups/
├── notebooks/
├── reports/
├── tests/
├── deployment/
├── monitoring/
├── infrastructure/
├── models/
├── research/
├── books/
├── datasets/
├── embeddings/
├── vector_db/
├── src/
```

---

# SRC

```
src/

├── main.py
├── app.py
├── bootstrap.py
├── scheduler.py
├── settings.py

├── core/
├── common/
├── api/
├── agents/
├── services/
├── workflows/
├── engines/
├── integrations/
├── infrastructure/
├── repositories/
├── database/
├── models/
├── schemas/
├── utils/
├── telemetry/
├── learning/
├── research/
├── execution/
├── monitoring/
├── reports/
├── telegram/
├── mt5/
```

---

# AGENTS

```
agents/

chief_ai/

technical/

market_structure/

price_action/

smart_money/

ict/

wyckoff/

elliott/

volume_profile/

order_flow/

vwap/

liquidity/

support_resistance/

pattern_recognition/

trend/

volatility/

macro/

fed/

ecb/

boj/

pboc/

inflation/

employment/

gdp/

bonds/

dxy/

etf/

cot/

news/

historical/

machine_learning/

statistics/

risk/

execution/

learning/

books/

monitoring/
```

---

# ENGINES

```
engines/

market_engine/

risk_engine/

execution_engine/

learning_engine/

historical_engine/

news_engine/

macro_engine/

technical_engine/

similarity_engine/

backtesting_engine/

ml_engine/

statistics_engine/

journal_engine/

book_engine/

confidence_engine/

probability_engine/

monitoring_engine/
```

---

# WORKFLOWS

```
workflows/

startup/

shutdown/

market_update/

news/

macro/

trade/

execution/

learning/

research/

backtesting/

optimization/

reporting/

maintenance/
```

---

# SERVICES

```
services/

market/

macro/

news/

telegram/

mt5/

database/

embeddings/

vector_search/

feature_engineering/

backtesting/

optimization/

statistics/

reports/

journal/

scheduler/
```

---

# DATABASE

```
database/

postgres/

redis/

qdrant/

migrations/

repositories/

seed/

backup/

restore/
```

---

# CONFIG

```
config/

development.yaml

testing.yaml

demo.yaml

production.yaml

risk.yaml

telegram.yaml

mt5.yaml

logging.yaml

monitoring.yaml

database.yaml

agents.yaml

ml.yaml

books.yaml

research.yaml

news.yaml

macro.yaml
```

---

# BOOKS

```
books/

uploaded/

processed/

ocr/

chunks/

metadata/

validation/

knowledge_graph/
```

---

# EMBEDDINGS

```
embeddings/

books/

news/

research/

historical/

journal/

market/

strategies/
```

---

# DATASETS

```
datasets/

ticks/

candles/

macro/

news/

economic/

historical/

cot/

etf/

dxy/

yields/

volatility/

sessions/
```

---

# REPORTS

```
reports/

daily/

weekly/

monthly/

research/

signals/

performance/

backtests/

learning/

optimization/

system/
```

---

# LOGS

```
logs/

application/

agents/

errors/

mt5/

telegram/

research/

execution/

learning/

database/

api/

performance/
```

---

# MONITORING

```
monitoring/

grafana/

prometheus/

alerts/

dashboards/

metrics/

healthchecks/
```

---

# TESTS

```
tests/

unit/

integration/

performance/

load/

stress/

security/

historical/

backtesting/

agents/

telegram/

mt5/

database/
```

---

# RESEARCH

```
research/

books/

papers/

experiments/

hypotheses/

results/

statistics/

validation/

notes/
```

---

# NOTEBOOKS

```
notebooks/

exploration/

ml/

statistics/

historical/

macro/

news/

feature_engineering/
```

---

# MODELS

```
models/

production/

experimental/

archived/

validation/

registry/
```

---

# TELEGRAM

```
telegram/

bot/

commands/

handlers/

reports/

notifications/

journal/

dashboard/

keyboards/
```

---

# MT5

```
mt5/

connection/

orders/

positions/

history/

market/

risk/

execution/

monitoring/
```

---

# COMMON

```
common/

exceptions/

events/

logging/

security/

validation/

constants/

decorators/

mixins/

helpers/
```

---

# DOCUMENTATION

```
docs/

architecture/

agents/

api/

deployment/

development/

books/

research/

workflows/

decisions/

adr/

user_manual/
```

---

# INFRASTRUCTURE

```
infrastructure/

docker/

nginx/

grafana/

prometheus/

postgres/

redis/

qdrant/

backup/
```

---

# DEPLOYMENT

```
deployment/

development/

staging/

demo/

production/

scripts/
```

---

# NAMING RULES

Files

snake_case

Classes

PascalCase

Functions

snake_case

Variables

snake_case

Constants

UPPER_CASE

Database

snake_case

API

RESTful

---

# MODULE RULES

Every module must contain

README.md

__init__.py

config.py

models.py

service.py

repository.py

exceptions.py

schemas.py

tests/

logging.py

metrics.py

---

# FINAL RULE

No business logic may exist outside the defined architecture.

Every new feature must be placed into the correct module.

Architecture consistency has higher priority than development speed.