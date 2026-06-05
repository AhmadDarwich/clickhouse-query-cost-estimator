import time
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class TableEstimate:
    database: str
    table: str
    parts: int
    rows: int
    marks: int


@dataclass
class EstimateResult:
    query: str

    # EXPLAIN ESTIMATE results
    table_estimates: List[TableEstimate] = field(default_factory=list)
    total_rows: int = 0
    total_parts: int = 0
    total_marks: int = 0

    # EXPLAIN PLAN
    query_plan: str = ""

    # Timing (milliseconds)
    explain_time_ms: float = 0.0      # time to run EXPLAIN (analysis + planning)
    execution_time_ms: float = 0.0    # wall-clock time for full execution
    server_time_ms: float = 0.0       # server-side time reported by ClickHouse

    # Execution stats
    read_rows: int = 0
    read_bytes: int = 0
    result_rows: int = 0
    result_bytes: int = 0
    memory_usage_bytes: int = 0

    was_executed: bool = False

    # Errors (non-fatal — other steps still run)
    explain_error: Optional[str] = None
    execution_error: Optional[str] = None


class QueryEstimator:
    def __init__(self, client):
        self.client = client

    @staticmethod
    def _is_select(query: str) -> bool:
        first = query.strip().split()[0].upper() if query.strip() else ""
        return first in ("SELECT", "WITH")

    def estimate(self, query: str, execute: bool = True) -> EstimateResult:
        result = EstimateResult(query=query)
        is_select = self._is_select(query)

        # Step 1: EXPLAIN ESTIMATE — rows/parts/marks per table
        if is_select:
            try:
                t0 = time.perf_counter()
                er = self.client.query(f"EXPLAIN ESTIMATE {query}")
                result.explain_time_ms = (time.perf_counter() - t0) * 1000

                for row in er.result_rows:
                    te = TableEstimate(
                        database=str(row[0]),
                        table=str(row[1]),
                        parts=int(row[2]),
                        rows=int(row[3]),
                        marks=int(row[4]),
                    )
                    result.table_estimates.append(te)
                    result.total_rows += te.rows
                    result.total_parts += te.parts
                    result.total_marks += te.marks
            except Exception as e:
                result.explain_error = str(e)

        # Step 2: EXPLAIN PLAN — human-readable execution plan
        if is_select:
            try:
                pr = self.client.query(f"EXPLAIN PLAN {query}")
                result.query_plan = "\n".join(str(row[0]) for row in pr.result_rows)
            except Exception:
                pass

        # Step 3: Execute and collect real stats
        if execute:
            try:
                t0 = time.perf_counter()
                xr = self.client.query(query)
                result.execution_time_ms = (time.perf_counter() - t0) * 1000
                result.was_executed = True
                result.result_rows = len(xr.result_rows)

                summary = xr.summary or {}
                result.read_rows = int(summary.get("read_rows", 0))
                result.read_bytes = int(summary.get("read_bytes", 0))
                result.result_bytes = int(summary.get("result_bytes", 0))
                elapsed_ns = int(summary.get("elapsed_ns", 0))
                if elapsed_ns:
                    result.server_time_ms = elapsed_ns / 1_000_000

                # Memory usage lives in query_log; give the flush a moment
                query_id = getattr(xr, "query_id", None)
                if query_id:
                    time.sleep(0.05)
                    try:
                        mem_res = self.client.query(
                            "SELECT memory_usage FROM system.query_log "
                            "WHERE type = 'QueryFinish' AND query_id = {qid:String} LIMIT 1",
                            parameters={"qid": query_id},
                        )
                        if mem_res.result_rows:
                            result.memory_usage_bytes = int(mem_res.result_rows[0][0])
                    except Exception:
                        pass

            except Exception as e:
                result.execution_error = str(e)

        return result
