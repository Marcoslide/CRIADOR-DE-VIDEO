# infra/gpu — GPU Engine V1 (RTX 4090 studio node)

> Pacote executável de provisionamento/diagnóstico/benchmark/monitoramento para o nó GPU
> principal do Criador de Vídeo. **Decisão oficial de hardware da V1: NVIDIA RTX 4090
> (24GB VRAM)** — não a RTX 5090 cogitada num plano anterior (`claude/gpu-avatar-factory-spec`,
> `GPU_ENGINE_SETUP_PLAN.md`, ainda não mesclado à `main`). B200 fica reservada para uma
> fase futura de AI Heavy/Burst (treino, modelos >24GB, batches grandes) — ver seção
> "B200 — caminho futuro" abaixo. Nada deste diretório instala nada sozinho: cada script
> só roda quando alguém o executa explicitamente no nó real.

## Por que RTX 4090 é mais simples que o plano anterior de RTX 5090

A RTX 5090 (Blackwell, lançada jan/2025) exigia módulo de kernel NVIDIA open-source
obrigatório, CUDA 12.8+, TensorRT 10.8+ e recompilar FFmpeg para features novas do SDK
13.0 — tudo isso por ser hardware recém-lançado. A RTX 4090 (Ada Lovelace, no mercado
desde out/2022) é uma geração madura: driver proprietário fechado padrão funciona,
qualquer CUDA/TensorRT/PyTorch estável recente já suporta `sm_89` sem ressalva, e o
FFmpeg do apt padrão do Ubuntu 24.04 já cobre H.264/HEVC/AV1 via NVENC sem recompilar.

## Estrutura

```
infra/gpu/
  lib/common.sh          — biblioteca compartilhada (logging, dry-run, idempotência,
                            registro estruturado de resultados) — ADIÇÃO à estrutura
                            original da missão, para não duplicar boilerplate em ~25
                            scripts diferentes.
  bootstrap/00-10         — provisionamento sequencial (ver "Como rodar" abaixo)
  diagnostics/            — testes pontuais, cada um roda sozinho
  benchmarks/             — medição estruturada (JSON), usadas pelo relatório agregado
  unreal/ audio2face/ metahuman/  — preflight específico de cada engine de render
  config/versions.env     — fonte única de versões (nunca hardcoded nos scripts)
  config/gpu-engine.example.env  — template de configuração runtime (VRAM/disco/paths)
  reports/                — saída de GPU_ENGINE_REPORT_<timestamp>.json/.md
```

A lógica em Python mais pesada (VRAM Manager, Model Manager, GPU Orchestrator,
telemetria, geração de relatório, CLI) fica em `services/gpu_engine`
(`dhf_gpu_engine`) — um membro do workspace `uv` do monorepo, não duplicado aqui.
`infra/gpu/bootstrap/10-final-validation.sh --report` e
`infra/gpu/benchmarks/benchmark_report.py` chamam esse pacote em vez de reimplementar a
geração de relatório em bash.

## Vocabulário de status (nunca hardcoded)

Todo script desta árvore usa exatamente um destes valores — nunca inventa um PASS:

| Status | Significado |
|---|---|
| `PASS` | checagem real rodou e passou |
| `WARN` | checagem real rodou, achou algo não-ideal mas não bloqueante |
| `FAIL` | checagem real rodou e falhou — corrigível neste nó |
| `SKIP` | não se aplica aqui (ex.: encoder ausente do build, ou limitação de plataforma permanente como MetaHuman Animator no Linux — nunca contado como FAIL, porque nenhuma reinstalação resolve) |
| `NOT_TESTED` | dependência ausente para nem tentar o teste (ex.: PyTorch não instalado) |
| `REQUIRES_GPU` | tudo certo até aqui, mas depende de uma GPU real que não existe neste ambiente |

`bootstrap/10-final-validation.sh` só falha (exit 1) se houver `FAIL` de verdade —
`REQUIRES_GPU`/`NOT_TESTED`/`SKIP` nunca bloqueiam o bootstrap, só documentam
honestamente o que não pôde ser confirmado aqui.

## Como rodar

```bash
cd infra/gpu/bootstrap
./00-preflight.sh              # nunca instala nada — só audita e aborta em FAIL crítico
./01-system.sh                 # timezone, usuário, hot storage local
./02-nvidia-driver.sh          # requer reboot depois se instalar de novo
./03-cuda.sh
./04-tensorrt.sh
./05-docker.sh
./06-nvidia-container-toolkit.sh
./07-media-stack.sh
./08-python-ai.sh
./09-monitoring.sh
./10-final-validation.sh --report
```

Todos aceitam `--dry-run` (mostra o que faria, não executa nada). Todos são idempotentes
— rodar de novo pula o que já está no estado certo.

Diagnóstico pontual, a qualquer momento (não precisa do bootstrap completo):

```bash
infra/gpu/diagnostics/gpu-info.sh --json
python3 infra/gpu/diagnostics/cuda-test.py --json
python3 infra/gpu/diagnostics/pytorch-test.py --json
python3 infra/gpu/diagnostics/tensorrt-test.py --json
infra/gpu/diagnostics/nvenc-test.sh
```

Preflight de cada engine de render (não instalam nada, só avaliam se é possível instalar):

```bash
infra/gpu/unreal/preflight.sh        # → UNREAL_READY_FOR_INSTALL: YES/NO
infra/gpu/audio2face/preflight.sh    # → AUDIO2FACE_READY_FOR_INSTALL: YES/NO
infra/gpu/metahuman/preflight.sh     # → LINUX_SUPPORTED_COMPONENTS / WINDOWS_ONLY_COMPONENTS
infra/gpu/audio2face/unreal-compatibility-gate.sh   # → AUDIO2FACE_UNREAL_COMPATIBILITY
```

## Validado neste ambiente de desenvolvimento (sem GPU real)

Este sandbox **é** Ubuntu 24.04.4 LTS de verdade (confirmado via `/etc/os-release`), só
não tem GPU NVIDIA. Isso permitiu validar de ponta a ponta a parte que não depende de
hardware: `00-preflight.sh` roda e reporta corretamente (inclusive `FAIL` genuíno de
RAM/disco/rede — este sandbox tem menos recursos que a instância contratada, isso é
esperado); `ffmpeg-test.sh` fez encode/decode real via libx264; `disk-benchmark.sh` e
`benchmark_disk.py` mediram write/read reais; `network-benchmark.sh` detectou
corretamente o bloqueio de rede deste sandbox a `developer.download.nvidia.com` e
`download.pytorch.org` (mesma política de proxy documentada nas sessões anteriores deste
projeto); todos os testes/preflights que precisam de GPU reportaram honestamente
`REQUIRES_GPU`/`NOT_TESTED`, nunca um `PASS` fingido.

**Dois bugs reais de bash foram encontrados e corrigidos rodando estes scripts de
verdade** (não só lendo o código): `curl -w '...'` e `grep -c` imprimem uma saída
parcial mesmo quando retornam código de erro — um padrão `comando_que_imprime || echo
fallback` dentro de `$(...)` faz as duas saídas se concatenarem em vez do fallback
substituir a primeira. Corrigido em `network-benchmark.sh` e `unreal/preflight.sh`
separando a captura do exit code da decisão de fallback.

## Riscos identificados nesta rodada de pesquisa (fontes oficiais, ver `config/versions.env`)

1. **MetaHuman Animator é Windows-only** (depende de DirectX 12) — confirmado na
   documentação oficial da Epic. A etapa de Identity/Performance do MetaHuman Creator
   também fica desabilitada no Linux pela mesma razão. Decisão pendente do Marcos: uma
   instância Windows adicional só para essa etapa, ou aceitar a limitação por enquanto
   (o resto do pipeline — montagem de MetaHuman, Unreal, render — funciona no Linux).
2. **Unreal Engine no Linux não tem binário oficial do Editor via launcher** — o único
   caminho documentado é compilar do código-fonte, com a conta GitHub vinculada à conta
   Epic (`dev.epicgames.com/documentation/unreal-engine/downloading-source-code-in-unreal-engine`)
   — uma autorização manual, não automatizável por script.
3. **Audio2Face-3D exige NGC_API_KEY** (conta NVIDIA Developer Program) para baixar o
   container NIM ou usar a API hospedada em `build.nvidia.com`. Self-host de
   dev/pesquisa é gratuito (até 16 GPUs, sem SLA); produção exige licença NVIDIA AI
   Enterprise paga ou uso via API hospedada com custo por uso.
4. **A maior parte desta pesquisa veio de busca indexada, não de leitura direta das
   páginas oficiais** — `docs.nvidia.com`, `developer.nvidia.com`, `pytorch.org` e
   `dev.epicgames.com` estão bloqueados pela política de rede deste ambiente de
   desenvolvimento (mesmo bloqueio já documentado em sessões anteriores deste projeto
   para `ghcr.io`/Docker Hub). Os números em `config/versions.env` devem ser
   reconfirmados manualmente antes de rodar em produção — os `diagnostics/` fazem
   exatamente essa reconfirmação em runtime.

## VRAM Manager / Model Manager / GPU Orchestrator

Bases reais (não simulação) em `services/gpu_engine` — ver o README desse pacote para a
API completa. Resumo: RTX 4090 tem 24576MB de VRAM total (`config/gpu-engine.example.env`);
o VRAM Manager rastreia HOT/WARM/UNLOADED por consumidor nomeado (Audio2Face, TTS,
upscaler, modelo generativo) com thresholds de warning/critical configuráveis (defaults:
80%/92%); o Model Manager decide load/unload consultando o VRAM Manager antes de admitir
um novo modelo; o GPU Orchestrator expõe tudo isso (`get_status`, `get_capabilities`,
`get_health`, `run_benchmark`, `get_loaded_models`, `prepare_job`, `release_job`) via CLI
(`dhf-gpu`) — deliberadamente **não conectado a `apps/api`/`apps/web` nesta rodada**, para
não conflitar com o trabalho paralelo em andamento no monorepo (Google Drive, Avatar
Factory). A integração com o Dashboard fica para um card futuro.

## B200 — caminho futuro (arquitetura apenas, nada instalado)

```
provider: B200
capabilities: AI_HEAVY
usos previstos: geração de vídeo em larga escala, treino/fine-tuning, modelos >24GB, batches grandes
```

Roteamento de carga conceitual (não provisiona nada automaticamente):

```
UNREAL_RENDER          → RTX class (4090)
METAHUMAN               → RTX class (4090)
VIDEO_ENCODE (NVENC)    → GPU com NVENC (4090)
AUDIO2FACE              → qualquer GPU suportada (4090 serve, ~2-4.5GB/stream)
GENERATIVE_SMALL/MEDIUM → RTX 4090
GENERATIVE_LARGE        → B200
TRAINING                → B200
```

B200 só entra quando houver ganho comprovado (harness de comparação 4090×B200 — mesmo
modelo/input/parâmetros, medindo qualidade/tempo/VRAM/custo/throughput — é trabalho
futuro, não implementado nesta rodada).

## O que ainda depende da RTX 4090 real (Hostinger)

Tudo que este README marca como `REQUIRES_GPU`/`NOT_TESTED` nesta rodada: validação
funcional de driver/CUDA/TensorRT/NVENC, os benchmarks de `benchmarks/`, o preflight
completo de Unreal/Audio2Face rodando ponta a ponta, e o gate de compatibilidade
Audio2Face×Unreal (que exige os dois instalados). Nada disso é simulável sem a GPU —
por isso os scripts existem prontos para rodar assim que o nó existir, em vez de uma
promessa de "vamos escrever depois".
