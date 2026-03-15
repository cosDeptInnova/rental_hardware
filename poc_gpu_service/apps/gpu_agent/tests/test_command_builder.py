from apps.gpu_agent.services.command_builder import build_llama_command


def test_command_builder():
    cmd = build_llama_command('C:/llama/llama-server.exe', 'D:/m/model.gguf', '127.0.0.1', 9001, 'CUDA0', 4096, 2)
    assert '--model' in cmd
    assert 'CUDA0' in cmd
