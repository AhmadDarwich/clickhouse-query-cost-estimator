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

### Large queries

For big, multi-line queries (hundreds or thousands of lines) you don't want to
wrestle with shell quoting. Read the query from a file or pipe it in instead:

```bash
# From a file — the cleanest option for huge queries
chqce -f report.sql

# Piped via stdin
cat report.sql | chqce
chqce < report.sql

# If ClickHouse rejects it with a max_query_size error, raise the limit
chqce -f report.sql --max-query-size 1048576   # 1 MiB
```

The query source is resolved in this priority order:

1. `--file` / `-f` — read from a file
2. `QUERY` argument — passed on the command line
3. piped **stdin** — when input isn't a terminal
4. interactive prompt — when nothing else is provided

The echoed query is truncated to the first 30 lines in the output, so a large
query never buries the results.

### Timeouts and resource limits

Heavy queries can hit server-side limits. The tool catches these, reports them
clearly, and tells you which flag gets you unstuck:

```bash
# Abort the query after 5 minutes instead of waiting indefinitely
chqce -t 300 "SELECT ... a slow aggregation ..."

# Fix "AST is too big" (e.g. a giant IN (...) list)
chqce -f report.sql --max-ast-elements 500000

# Fix "Max query size exceeded"
chqce -f report.sql --max-query-size 1048576   # 1 MiB
```

When a query fails, the error is classified and shown with suggestions. For
example, a timeout renders as:

```
╭──────────────────────────────────────────────────────────────╮
│ ✗  Execution error  Query timed out                          │
│ Code: 159. DB::Exception: Timeout exceeded: elapsed 30 ...   │
│                                                              │
│ Suggestions                                                  │
│ The query exceeded its time budget. Try:                     │
│   • raise the limit:  --timeout 600  (seconds, 0 = unlimited)│
│   • estimate without running:  --no-execute                  │
│   • narrow the query with a WHERE filter or LIMIT            │
╰──────────────────────────────────────────────────────────────╯
```

Recognized failures: **timeout**, **AST too big**, **parser depth**,
**query size**, **memory limit**, and **read-row/byte limits**.

## Options

| Flag | Env var | Default | Description |
|---|---|---|---|
| `--file` / `-f` | — | — | Read the query from a file (best for huge queries) |
| `--host` / `-H` | `CLICKHOUSE_HOST` | `localhost` | ClickHouse host |
| `--port` / `-p` | `CLICKHOUSE_PORT` | `8123` | HTTP port |
| `--user` / `-u` | `CLICKHOUSE_USER` | `default` | Username |
| `--password` / `-P` | `CLICKHOUSE_PASSWORD` | _(empty)_ | Password |
| `--database` / `-d` | `CLICKHOUSE_DATABASE` | `default` | Default database |
| `--timeout` / `-t` | — | `0` _(unlimited)_ | Server-side `max_execution_time` in seconds |
| `--max-query-size` | — | _(server default 262144)_ | Raise ClickHouse `max_query_size` for very large queries |
| `--max-ast-elements` | — | _(server default 50000)_ | Raise ClickHouse `max_ast_elements` for queries with huge ASTs |
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
