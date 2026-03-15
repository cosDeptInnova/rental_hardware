import argparse
import json
from apps.gpu_agent.services.model_service import ensure_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_alias", required=True)
    args = parser.parse_args()
    print(json.dumps(ensure_model(args.model_alias), indent=2))


if __name__ == "__main__":
    main()
