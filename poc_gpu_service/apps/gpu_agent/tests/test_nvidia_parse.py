from apps.gpu_agent.services.metrics_service import parse_csv


def test_parse_csv():
    raw = '0, GPU-123, L40S, 10, 20, 3000, 120, 50\n'
    rows = parse_csv(raw)
    assert rows[0][0] == '0'
    assert rows[0][2] == 'L40S'
