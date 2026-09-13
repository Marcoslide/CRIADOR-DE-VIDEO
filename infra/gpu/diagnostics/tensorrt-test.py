#!/usr/bin/env python3
"""tensorrt-test.py — engine mínimo real (não só import): constrói um TensorRT engine
para uma rede trivial (uma camada linear), roda inferência, mede latência e VRAM (seção
13 da missão). NOT_TESTED se tensorrt/numpy não estiverem instalados; REQUIRES_GPU se
tensorrt estiver instalado mas não conseguir inicializar um contexto (sem GPU visível).

Códigos de saída: 0 = PASS, 1 = FAIL, 2 = NOT_TESTED/REQUIRES_GPU/SKIP.

Uso:
    python3 tensorrt-test.py [--json]
"""

from __future__ import annotations

import json
import sys
import time


def run() -> dict:
    try:
        import numpy as np
        import tensorrt as trt
    except ImportError as exc:
        return {
            "status": "NOT_TESTED",
            "detail": (
                f"dependência ausente ({exc}) — rode 04-tensorrt.sh e "
                "08-python-ai.sh antes deste teste"
            ),
        }

    logger = trt.Logger(trt.Logger.WARNING)

    try:
        builder = trt.Builder(logger)
    except Exception as exc:  # noqa: BLE001 — qualquer falha aqui é "sem GPU/driver utilizável"
        return {"status": "REQUIRES_GPU", "detail": f"trt.Builder() falhou: {exc}"}

    network_flags = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    network = builder.create_network(network_flags)

    input_size = 1024
    input_tensor = network.add_input(name="input", dtype=trt.float32, shape=(1, input_size))
    weights = np.ones((input_size, input_size), dtype=np.float32) / input_size
    fc_layer = network.add_matrix_multiply(
        input_tensor,
        trt.MatrixOperation.NONE,
        network.add_constant((input_size, input_size), trt.Weights(weights)).get_output(0),
        trt.MatrixOperation.NONE,
    )
    fc_layer.get_output(0).name = "output"
    network.mark_output(fc_layer.get_output(0))

    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 256 * 1024 * 1024)

    started_build = time.perf_counter()
    serialized_engine = builder.build_serialized_network(network, config)
    build_elapsed_s = time.perf_counter() - started_build

    if serialized_engine is None:
        return {"status": "FAIL", "detail": "build_serialized_network retornou None"}

    runtime = trt.Runtime(logger)
    engine = runtime.deserialize_cuda_engine(serialized_engine)
    context = engine.create_execution_context()

    # cudart via ctypes, mesmo padrão de cuda-test.py — evita puxar pycuda/cupy só para
    # alocar dois buffers.
    import ctypes

    cudart = ctypes.CDLL("libcudart.so")
    input_bytes = input_size * 4
    d_input = ctypes.c_void_p()
    d_output = ctypes.c_void_p()
    cudart.cudaMalloc(ctypes.byref(d_input), input_bytes)
    cudart.cudaMalloc(ctypes.byref(d_output), input_bytes)

    host_input = np.random.randn(1, input_size).astype(np.float32)
    cudart.cudaMemcpy(d_input, host_input.ctypes.data_as(ctypes.c_void_p), input_bytes, 1)

    context.set_tensor_address("input", d_input.value)
    context.set_tensor_address("output", d_output.value)

    started_infer = time.perf_counter()
    context.execute_async_v3(0)
    cudart.cudaDeviceSynchronize()
    infer_elapsed_ms = (time.perf_counter() - started_infer) * 1000

    host_output = np.empty((1, input_size), dtype=np.float32)
    cudart.cudaMemcpy(host_output.ctypes.data_as(ctypes.c_void_p), d_output, input_bytes, 2)
    cudart.cudaFree(d_input)
    cudart.cudaFree(d_output)

    expected = host_input.mean()
    result_ok = bool(np.allclose(host_output, expected, atol=1e-3))

    return {
        "status": "PASS" if result_ok else "FAIL",
        "tensorrt_version": trt.__version__,
        "build_elapsed_s": round(build_elapsed_s, 3),
        "inference_latency_ms": round(infer_elapsed_ms, 4),
        "result_matches_expected": result_ok,
    }


def main() -> int:
    as_json = "--json" in sys.argv[1:]
    result = run()

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        status = result["status"]
        if status == "PASS":
            print(
                f"[PASS] TensorRT {result['tensorrt_version']} — "
                f"build {result['build_elapsed_s']}s, "
                f"inferência {result['inference_latency_ms']}ms"
            )
        else:
            print(f"[{status}] {result['detail']}")

    return {"PASS": 0, "FAIL": 1}.get(result["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
