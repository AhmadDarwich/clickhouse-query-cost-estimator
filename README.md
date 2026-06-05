# clickhouse-query-cost-estimator

A terminal CLI that estimates the cost of a ClickHouse SQL query **before you regret running it**, and helps you tune indexes afterwards.

```
╭──────────────────────────────────────────────────────────────╮
│ ClickHouse Query Cost Estimator  v0.1.0                      │
│ Connected to localhost:8123  ·  database: default  ·  23.8  │
╰──────────────────────────────────────────────────────────────╯

Cost Estimate  (from EXPLAIN ESTIMATE)
 Database  Table   Parts  Est. Rows  Marks
 default   orders     12    4.5M     550

Timing
 Phase                       Time        Notes
 SQL Analyzer (EXPLAIN)      2.1 ms      parsing + plan generation
 Execution (client)        234.5 ms      wall-clock including network
 Execution (server)        228.3 ms      server-side only

Execution Stats
 Rows read      4.5M      Bytes read   1.2 GB
 Result rows    18.2K     Peak memory  45.6 MB

── Index Suggestions ──────────────────────────────────────────
  ✓  created_at  —  already in ORDER BY
  ⚠  user_id    —  not in ORDER BY
     ALTER TABLE default.orders
         ADD INDEX idx_orders_user_id user_id
         TYPE bloom_filter(0.01) GRANULARITY 4;
```

## What it tells you

| Metric | Source |
|---|---|
| **Estimated rows / parts / marks** | `EXPLAIN ESTIMATE` |
| **SQL analyzer time** | time to run `EXPLAIN PLAN` (parsing + planning) |
| **Execution time (client)** | wall-clock including network round-trip |
| **Execution time (server)** | `elapsed_ns` from `X-ClickHouse-Summary` header |
| **Rows / bytes read, peak memory** | `system.query_log` after execution |
| **Index suggestions** | `system.tables` ORDER BY vs WHERE columns |

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Analyze a single query
chqce "SELECT count() FROM hits WHERE EventDate = today()"

# Interactive mode — paste any query, then type ; or GO to submit
chqce

# Custom connection
chqce --host my.ch.host --port 9123 --user admin --database analytics \
      "SELECT count() FROM events WHERE user_id = 42"

# Estimate only — skip execution (safe for expensive/destructive queries)
chqce --no-execute "SELECT * FROM huge_table WHERE x > 0"
```

## Options

| Flag | Env var | Default | Description |
|---|---|---|---|
| `--host` / `-H` | `CLICKHOUSE_HOST` | `localhost` | ClickHouse host |
| `--port` / `-p` | `CLICKHOUSE_PORT` | `8123` | HTTP port |
| `--user` / `-u` | `CLICKHOUSE_USER` | `default` | Username |
| `--password` / `-P` | `CLICKHOUSE_PASSWORD` | _(empty)_ | Password |
| `--database` / `-d` | `CLICKHOUSE_DATABASE` | `default` | Default database |
| `--no-execute` | — | `false` | Skip actual execution; estimate only |

## Interactive mode

Type or paste a multi-line query, then submit by:
- Ending the last line with `;`
- Typing `GO` on its own line

Press **Ctrl+C** to exit.

## How index suggestions work

1. The query is parsed with [sqlglot](https://github.com/tobymao/sqlglot) to extract WHERE-clause columns and condition types (equality, range, LIKE, IN).
2. Each referenced table's `sorting_key` is fetched from `system.tables`.
3. Columns not covered by the sort key get a skip-index `ALTER TABLE` suggestion, with the type chosen by condition and column type:

| Condition | Column type | Suggested index |
|---|---|---|
| `LIKE` / `ILIKE` | any | `tokenbf_v1(32768, 3, 0)` |
| `>` / `<` / `BETWEEN` | any | `minmax` |
| `=` / `IN` | String | `bloom_filter(0.01)` |
| `=` / `IN` | numeric / date | `set(100)` |

## Requirements

- Python ≥ 3.9
- ClickHouse with HTTP interface enabled (default port 8123)
