import json
from apps.gpu_agent.services.metrics_service import collect_gpu_metrics


if __name__ == "__main__":
    print(json.dumps(collect_gpu_metrics(), indent=2))
