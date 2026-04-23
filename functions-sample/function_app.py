import csv
import datetime
import decimal
import io
import json
import os
from pathlib import Path

import azure.functions as func


# FunctionApp 是 Python v2 编程模型的入口对象。
# 这里为了本地测试方便使用 ANONYMOUS，调用 HTTP trigger 时不需要 function key。
# 如果部署到真实 Azure 环境，业务接口通常应改为 FUNCTION 或按路由单独设置 auth_level，
# 避免未授权用户直接访问公开 URL。
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# GET /api/csv-summary 默认读取这个示例 CSV。
SAMPLE_CSV_PATH = Path(__file__).resolve().parent / "data" / "sample_sales.csv"
DEFAULT_PREVIEW_LIMIT = 5
MAX_PREVIEW_LIMIT = 20
DEFAULT_CSV_MAX_BYTES = 1_048_576


def _json_response(payload: dict, status_code: int = 200) -> func.HttpResponse:
    """把 Python dict 统一包装成 JSON HTTP 响应。"""
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=True),
        status_code=status_code,
        mimetype="application/json",
    )


def _error_response(message: str, status_code: int = 400) -> func.HttpResponse:
    """返回统一格式的错误响应，方便客户端读取 error 字段。"""
    return _json_response({"error": message}, status_code=status_code)


def _parse_preview_limit(req: func.HttpRequest) -> int:
    """读取 query string 里的 preview 参数，并限制最大预览行数。"""
    raw_value = req.params.get("preview")
    if not raw_value:
        return DEFAULT_PREVIEW_LIMIT

    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_PREVIEW_LIMIT

    return max(0, min(value, MAX_PREVIEW_LIMIT))


def _number_for_json(value: decimal.Decimal) -> int | float:
    """Decimal 不能直接 JSON 序列化，这里转换成 int 或 float。"""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _csv_summary(csv_text: str, preview_limit: int) -> dict:
    """解析 CSV 文本，返回行数、列名、数值列统计和预览数据。"""
    reader = csv.DictReader(io.StringIO(csv_text))
    raw_columns = reader.fieldnames or []
    columns = [column.strip() if column else "" for column in raw_columns]

    # demo 要求第一行必须是唯一且非空的表头。
    if not columns or any(not column for column in columns):
        raise ValueError("CSV header row is required and column names cannot be empty.")

    if len(set(columns)) != len(columns):
        raise ValueError("CSV column names must be unique.")

    numeric_stats: dict[str, dict] = {}
    preview_rows = []
    row_count = 0

    for raw_row in reader:
        # DictReader 会按原始表头返回数据，这里统一映射到清理后的列名。
        clean_row = {
            columns[index]: (raw_row.get(raw_columns[index]) or "").strip()
            for index in range(len(raw_columns))
        }

        # 跳过完全空白的行。
        if not any(clean_row.values()):
            continue

        row_count += 1
        if len(preview_rows) < preview_limit:
            preview_rows.append(clean_row)

        # 尝试把每个字段解析成 Decimal；解析失败则视为普通文本列。
        for column, value in clean_row.items():
            if not value:
                continue

            try:
                number = decimal.Decimal(value.replace(",", ""))
            except decimal.InvalidOperation:
                continue

            stats = numeric_stats.setdefault(
                column,
                {
                    "count": 0,
                    "sum": decimal.Decimal("0"),
                    "min": number,
                    "max": number,
                },
            )
            stats["count"] += 1
            stats["sum"] += number
            stats["min"] = min(stats["min"], number)
            stats["max"] = max(stats["max"], number)

    # Decimal 统计值转换成 JSON 可序列化的数字。
    serializable_stats = {}
    for column, stats in numeric_stats.items():
        average = stats["sum"] / stats["count"]
        serializable_stats[column] = {
            "count": stats["count"],
            "sum": _number_for_json(stats["sum"]),
            "min": _number_for_json(stats["min"]),
            "max": _number_for_json(stats["max"]),
            "average": _number_for_json(average),
        }

    return {
        "rowCount": row_count,
        "columns": columns,
        "numericColumns": serializable_stats,
        "preview": preview_rows,
    }


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    """健康检查接口：GET /api/health。"""
    return _json_response(
        {
            "status": "ok",
            "app": "functions-sample",
            "timestampUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    )


@app.route(route="hello", methods=["GET", "POST"])
def hello(req: func.HttpRequest) -> func.HttpResponse:
    """基础 HTTP trigger 示例：支持 query string 和 JSON body。"""
    name = req.params.get("name")

    if not name and req.method == "POST":
        try:
            body = req.get_json()
        except ValueError:
            body = {}

        if isinstance(body, dict):
            name = body.get("name")

    name = name or "local developer"

    return _json_response(
        {
            "message": f"Hello, {name}!",
            "environment": os.getenv("APP_ENV", "local"),
            "workerRuntime": os.getenv("FUNCTIONS_WORKER_RUNTIME", "python"),
            "timestampUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    )


@app.route(route="csv-summary", methods=["GET", "POST"])
def csv_summary(req: func.HttpRequest) -> func.HttpResponse:
    """CSV 处理 demo：GET 读本地样例文件，POST 处理请求体里的 CSV。"""
    preview_limit = _parse_preview_limit(req)
    max_bytes = int(os.getenv("CSV_MAX_BYTES", DEFAULT_CSV_MAX_BYTES))

    if req.method == "POST":
        # POST 模式适合模拟“用户上传 CSV 内容”的场景。
        body = req.get_body()
        if not body:
            return _error_response("POST body must contain CSV text.")
        if len(body) > max_bytes:
            return _error_response(
                f"CSV body is too large. Max size is {max_bytes} bytes.",
                status_code=413,
            )
        source = "request-body"
        csv_text = body.decode("utf-8-sig")
    else:
        # GET 模式方便快速验证，不需要手动构造请求体。
        source = str(SAMPLE_CSV_PATH.relative_to(Path(__file__).resolve().parent))
        csv_text = SAMPLE_CSV_PATH.read_text(encoding="utf-8-sig")

    try:
        summary = _csv_summary(csv_text, preview_limit)
    except ValueError as exc:
        return _error_response(str(exc))

    summary.update(
        {
            "source": source,
            "previewLimit": preview_limit,
            "timestampUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    )
    return _json_response(summary)
