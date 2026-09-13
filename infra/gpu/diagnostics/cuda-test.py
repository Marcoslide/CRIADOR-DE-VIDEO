#!/usr/bin/env python3
"""cuda-test.py — teste real da CUDA Runtime API via ctypes (libcudart.so), sem depender
de PyTorch/TensorRT estarem instalados — prova que o CUDA Toolkit em si funciona antes de
qualquer camada de mais alto nível (essas têm teste próprio: pytorch-test.py,
tensorrt-test.py). Não é "nvcc --version": aloca memória de verdade na GPU, copia dados
ida e volta, e mede o tempo — seção 12 da missão.

Códigos de saída: 0 = PASS, 1 = FAIL (CUDA presente mas o teste falhou), 2 = NOT_TESTED
(biblioteca CUDA não encontrada — normal antes do bootstrap ou sem GPU).

Uso:
    python3 cuda-test.py [--json]
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import sys
import time

CUDA_SUCCESS = 0


def _find_libcudart() -> str | None:
    # ctypes.util.find_library nem sempre acha libcudart (nome versionado, ex.
    # libcudart.so.13) — tenta um punhado de nomes plausíveis antes de desistir.
    candidates = [
        ctypes.util.find_library("cudart"),
        "libcudart.so",
        "libcudart.so.13",
        "libcudart.so.12",
        "/usr/local/cuda/lib64/libcudart.so",
    ]
    for name in candidates:
        if not name:
            continue
        try:
            ctypes.CDLL(name)
            return name
        except OSError:
            continue
    return None


def run() -> dict:
    lib_name = _find_libcudart()
    if lib_name is None:
        return {
            "status": "NOT_TESTED",
            "detail": (
                "libcudart.so não encontrada — instale o CUDA Toolkit (03-cuda.sh) "
                "antes deste teste"
            ),
        }

    cudart = ctypes.CDLL(lib_name)

    device_count = ctypes.c_int(0)
    rc = cudart.cudaGetDeviceCount(ctypes.byref(device_count))
    if rc != CUDA_SUCCESS or device_count.value == 0:
        return {
            "status": "REQUIRES_GPU",
            "detail": (
                f"cudaGetDeviceCount retornou rc={rc}, count={device_count.value} "
                "— sem GPU CUDA visível"
            ),
        }

    rc = cudart.cudaSetDevice(0)
    if rc != CUDA_SUCCESS:
        return {"status": "FAIL", "detail": f"cudaSetDevice(0) falhou com rc={rc}"}

    class CudaDeviceProp(ctypes.Structure):
        # Layout real de cudaDeviceProp tem dezenas de campos — só declaramos o
        # suficiente para name/major/minor/totalGlobalMem, que é tudo que usamos.
        # `name` tem 256 bytes reservados na struct real; o restante dos campos
        # importa apenas para o cálculo correto do offset em memória, não usamos
        # os valores.
        _fields_ = [
            ("name", ctypes.c_char * 256),
            ("uuid", ctypes.c_byte * 16),
            ("luid", ctypes.c_char * 8),
            ("luidDeviceNodeMask", ctypes.c_uint),
            ("totalGlobalMem", ctypes.c_size_t),
        ]

    prop = CudaDeviceProp()
    rc = cudart.cudaGetDeviceProperties(ctypes.byref(prop), 0)
    device_name = prop.name.decode(errors="replace") if rc == CUDA_SUCCESS else "desconhecido"
    total_mem_mb = (prop.totalGlobalMem / (1024 * 1024)) if rc == CUDA_SUCCESS else None

    major = ctypes.c_int(0)
    minor = ctypes.c_int(0)
    cudart.cudaDeviceGetAttribute(ctypes.byref(major), 75, 0)  # cudaDevAttrComputeCapabilityMajor
    cudart.cudaDeviceGetAttribute(ctypes.byref(minor), 76, 0)  # cudaDevAttrComputeCapabilityMinor
    compute_capability = f"{major.value}.{minor.value}"

    # Round-trip real: aloca 16MB no device, copia de um buffer host, copia de volta,
    # confirma que os bytes batem — prova que a GPU está genuinamente acessível para
    # compute, não só "visível" pelo driver.
    size_bytes = 16 * 1024 * 1024
    host_src = (ctypes.c_ubyte * size_bytes)(*[i % 256 for i in range(256)] * (size_bytes // 256))
    host_dst = (ctypes.c_ubyte * size_bytes)()
    device_ptr = ctypes.c_void_p()

    started = time.perf_counter()
    rc = cudart.cudaMalloc(ctypes.byref(device_ptr), size_bytes)
    if rc != CUDA_SUCCESS:
        return {"status": "FAIL", "detail": f"cudaMalloc({size_bytes} bytes) falhou com rc={rc}"}

    cudaMemcpyHostToDevice = 1
    cudaMemcpyDeviceToHost = 2
    rc = cudart.cudaMemcpy(device_ptr, host_src, size_bytes, cudaMemcpyHostToDevice)
    if rc == CUDA_SUCCESS:
        rc = cudart.cudaMemcpy(host_dst, device_ptr, size_bytes, cudaMemcpyDeviceToHost)
    cudart.cudaFree(device_ptr)
    elapsed_s = time.perf_counter() - started

    if rc != CUDA_SUCCESS:
        return {"status": "FAIL", "detail": f"cudaMemcpy falhou com rc={rc}"}

    roundtrip_ok = bytes(host_src) == bytes(host_dst)
    if not roundtrip_ok:
        return {
            "status": "FAIL",
            "detail": "round-trip host->device->host retornou dados diferentes do enviado",
        }

    return {
        "status": "PASS",
        "device_name": device_name,
        "compute_capability": compute_capability,
        "vram_total_mb": total_mem_mb,
        "roundtrip_bytes": size_bytes,
        "roundtrip_ok": True,
        "elapsed_s": round(elapsed_s, 6),
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
                f"[PASS] CUDA runtime funcional — {result['device_name']} "
                f"(cc {result['compute_capability']})"
            )
            print(f"       VRAM total: {result['vram_total_mb']:.0f}MB")
            print(
                f"       Round-trip de {result['roundtrip_bytes']} bytes em "
                f"{result['elapsed_s']}s — OK"
            )
        else:
            print(f"[{status}] {result['detail']}")

    return {"PASS": 0, "FAIL": 1}.get(result["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
