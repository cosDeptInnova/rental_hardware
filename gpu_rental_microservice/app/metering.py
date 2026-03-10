from prometheus_client import Counter, Histogram, Gauge

REQUESTS = Counter(
    "api_requests_total",
    "Total API requests",
    ["client_name", "path", "method", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "api_request_latency_seconds",
    "Request latency",
    ["client_name", "path", "method"],
)

JOB_GPU_SECONDS = Counter(
    "job_gpu_seconds_total",
    "Accumulated gpu seconds",
    ["client_name", "workload_name"],
)

RUNNING_JOBS = Gauge(
    "running_jobs",
    "Current running jobs",
    ["client_name"],
)
