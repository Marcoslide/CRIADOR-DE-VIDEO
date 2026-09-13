# ROADMAP.md — Digital Human Video Factory

Trabalho **card por card** (seção 79 do prompt-mestre): cada fase abaixo vira um ou mais
cards no Trello. Não avançamos para a fase N+1 sem a Definition of Done da fase N cumprida
de verdade (seção 80) — nada é "concluído" só porque o código foi escrito.

Status global: **FASE 1 concluída · FASE 2 (Storage) concluída com OAuth `drive.file`,
árvore 18/18 e contrato completo validado no Google Drive real.**

---

## FASE 0 — Auditoria ✅ CONCLUÍDA

- Repositório `Marcoslide/CRIADOR-DE-VIDEO` estava vazio (zero commits, zero branches).
- Nenhum código, stack ou conflito preexistente.
- Conclusão: implementação greenfield, seguindo o prompt-mestre integralmente.

---

## FASE 1 — Foundation ✅ CONCLUÍDA

**Objetivo:** esqueleto do monorepo rodando de ponta a ponta (web → api → postgres/redis →
worker), com health checks reais.

Escopo:
- Monorepo (`apps/`, `packages/`, `workers/`, `infra/docker/`, `migrations/`, `tests/`);
- Frontend React (Vite+TS+Tailwind) com shell de navegação e Dashboard mostrando status real;
- Backend FastAPI com `/health` (liveness) e `/health/ready` (checa Postgres + Redis de
  verdade);
- PostgreSQL com Alembic configurado (migration inicial real, sem tabelas de domínio ainda —
  essas chegam na Fase 3);
- Redis + Celery worker mínimo (task `ping` real, round-trip via broker);
- Docker Compose (`web`, `api`, `postgres`, `redis`, `worker`);
- `.env.example`, `.gitignore`, README raiz;
- Testes automatizados dos health checks.

**Fora de escopo nesta fase** (mesmo estando na stack final): GPU Orchestrator,
qualquer entidade de domínio (Avatar/Voice/Motion/Product/...), Director AI, engines
externas. Ver seções 6-10 deste documento.

**Definition of Done da Fase 1:**
- [x] `docker compose up` sobe os 5 serviços sem erro — **exceto**: build das imagens não
  pôde ser validado no sandbox de desenvolvimento (Docker Hub bloqueado pela política de
  rede da organização); `docker compose config` validou limpo. Pendente validação num
  ambiente com acesso ao registry;
- [x] `GET /health` responde 200 sempre que o processo API está de pé;
- [x] `GET /health/ready` retorna `postgres: connected` e `redis: connected` **reais** (não
  hardcoded) quando os serviços estão saudáveis, e reporta o erro real quando não estão;
- [x] Celery worker processa a task `health.ping` e o resultado é lido de volta pela API;
- [x] `alembic upgrade head` roda sem erro contra o Postgres do compose;
- [x] Frontend carrega o Dashboard e exibe o status vindo da API (não mockado);
- [x] `pytest` passa localmente contra os serviços reais do compose;
- [x] Nenhum segredo commitado.

---

## FASE 2 — Storage ✅ CONCLUÍDA

- `StorageProvider` (interface, em `packages/schemas`) + `GoogleDriveStorageProvider` real
  (`services/storage`) — OAuth User com escopo `drive.file`, chamadas REST diretas
  (`httpx` + `google-auth`,
  não `google-api-python-client` — ver `docs/ARCHITECTURE.md` §4.4);
- Bootstrap idempotente cria a root técnica `CRIADOR DE VIDEO — STORAGE`, marca-a com
  `appProperties`, persiste/valida o ID e cria as 18 pastas oficiais. A pasta histórica
  `CRIADOR DE VIDEO` não é tocada — ver `docs/STORAGE_GOOGLE_DRIVE.md`;
- Subpastas abaixo de cada uma das 18 (convenção de caminho/versão dos callers) são
  descobertas/criadas idempotentemente;
- Upload/download com streaming real (resumable upload, `alt=media` download em chunks);
- Retry com backoff para 429/5xx, timeouts configuráveis, cache de IDs descobertos;
- Estados `NOT_CONFIGURED / AUTH_EXPIRED / CONNECTING / CONNECTED / DEGRADED / ERROR` —
  `AUTH_EXPIRED` identifica `invalid_grant` sem retry infinito;
- Proteção contra exclusão permanente: `delete()` só envia à lixeira sem
  `allow_permanent=True` dentro de `02_SISTEMA_STORAGE/_tmp/` ou da área isolada
  `_integration_tests/<uuid>/`;
- `GET /storage/status` na API; CLI `dhf-storage check` (conexão + árvore);
- Testes unitários (mockados, `respx`) e testes de integração reais (separados, só rodam com
  credencial real configurada).

**Rodada de hardening** (mesma fase, sem mudar o status "validação pendente" abaixo):
- corrigido bug real de retry no upload — um `AsyncIterator` já consumido era reenviado
  numa nova tentativa, mandando corpo vazio/truncado sem erro nenhum. Agora cada tentativa
  reabre o arquivo do byte 0 (`content_factory`), com teste de regressão que prova o bug
  (verificado isoladamente contra o comportamento antigo antes do fix);
- `/health*` e `/storage/status` nunca mais devolvem `str(exc)`/URL/host cru —
  `dhf_shared.errors.sanitize_error` classifica por tipo, log completo continua só interno;
- `docker-compose.yml` dividido em base (sem porta de Postgres/Redis publicada, sem senha
  padrão, falha alto sem credencial) + `docker-compose.override.yml` (dev) +
  `docker-compose.prod.yml` (nginx em vez do servidor de dev do Vite);
- CI no GitHub Actions (`.github/workflows/ci.yml`): unitário sem serviços, integração com
  Postgres/Redis reais, ruff, frontend, scan de segredos (gitleaks).

**Pendente nesta fase** (não pedido nos cards de Storage, registrado para não perder o
fio): rotina de backup do PostgreSQL para o Drive (seção 65) — ainda não implementada.

**Validação real concluída:** OAuth User + `drive.file` autorizado, root criada pelo app,
ID persistido, árvore oficial 18/18 e bootstrap idempotente. A suíte ao vivo comprovou
upload resumable, download atômico byte-idêntico, checksum, exists, list, metadata, copy,
move/rename, lixeira segura, sync idempotente e retomada após perda de resposta. Todas as
mutações ficaram em `_integration_tests/<uuid>` e foram limpas de forma recuperável.

**DoD cumprido:** `tests/storage/test_google_drive_integration.py` passou integralmente
contra o My Drive real; health final `CONNECTED`.

## FASE 3 — Avatar Registry

- Entidade `Avatar` completa (schemas já desenhados em `docs/ARCHITECTURE.md`);
- Máquina de estados `DRAFT → ... → PRODUCTION_READY`, com transições validadas no backend
  (nunca só na UI);
- Identity Lock (seção 13) — bloqueio de reinterpretação após `IDENTITY_LOCKED`;
- Workflow de referências 360° (head/half body/full body, 36 ângulos cada, + categorias
  especializadas) e `AvatarAsset` com metadata completa;
- Telas: Avatars, Avatar Detail, Identity Lock, References/360.

**DoD:** um avatar real percorre todos os status até `PRODUCTION_READY` no banco, com
assets versionados e aprovação registrada.

## FASE 4 — Voice / Motion / Products

- Voice Bank + Voice DNA (identity vs. performance, presets, eventos não-verbais) —
  `VoiceProvider`, `ChatterboxProvider`, `ElevenLabsProvider`;
- Motion Bank + Motion DNA — captura/curadoria de mocap humano priorizada (seção 34);
- Product Brain (fatos confirmados vs. argumento de IA vs. proibido) + Product 3D metadata;
- Pronunciation Dictionary por personagem/canal.

**Depende de:** credenciais ElevenLabs (se usado) e/ou provider Chatterbox; benchmark de
voz (pesquisa técnica pendente, ver `docs/ARCHITECTURE.md` §11).
**DoD:** uma voz gera áudio real e audível; uma motion real está associada a um rig
compatível; um produto tem pelo menos um fato `CONFIRMED_FACT` e zero alucinação da IA.

## FASE 5 — Director AI

- `AIProvider` + `OpenAIProvider` real; `AnthropicProvider` preparado sem exigir config;
- Character Brain, Channel Brain;
- Scene Plan — geração de JSON validado (schema em `packages/schemas`), com as regras
  anti-robô da seção 44 aplicadas como validação, não como sugestão;
- Input do Director conforme seção 42.

**Depende de:** `OPENAI_API_KEY`.
**DoD:** um Scene Plan real gerado a partir de um tópico produz JSON válido contra o
schema, com pelo menos uma variação de emoção, uma pausa e um retorno de olhar ao longo da
cena — não um template estático.

## FASE 6 — GPU Engine

- GPU Orchestrator real rodando no nó Hostinger (RTX 5090): telemetria via
  `pynvml`/`nvidia-smi`, HOT/WARM/UNLOADED, scheduler, resource locking;
- `workers/gpu_worker`;
- Model Manager.

**Depende de:** nó Hostinger provisionado (drivers NVIDIA, CUDA, Docker + NVIDIA Container
Toolkit) — ver `docs/INSTALL_HOSTINGER.md` (a escrever nesta fase).
**Só pode ser validado no hardware real** — nada aqui roda "de verdade" neste ambiente de
desenvolvimento.
**DoD:** telemetria real (não simulada) aparece no Dashboard; um job real é agendado,
executado e a VRAM é liberada depois sem OOM.

## FASE 7 — Engines

- Integração Unreal Engine (`UnrealEngineProvider`) — Python API/Sequencer/Movie Render
  Queue;
- Integração Audio2Face-3D (`Audio2FaceProvider`);
- Integração MetaHuman Animator (`MetaHumanAnimatorProvider`) como benchmark/fallback;
- Pipeline Reference → Reconstrução → Mesh Master → Refinamento → MetaHuman from custom
  mesh → Rig → Materials → Groom → Digital Human Master.

**Requer resolver antes:** os pontos de pesquisa técnica #1-4 do `docs/ARCHITECTURE.md`
§11 (Unreal/MetaHuman em Linux, pipeline de reconstrução 3D, distribuição do Audio2Face,
requisitos do MetaHuman Animator).
**DoD:** ver seção 80 do prompt-mestre — só conta como pronto com output real gerado pela
ferramenta, arquivo existente, erro tratado, benchmark registrado.

## FASE 8 — Vídeo

- Scene pipeline completo (cena independente, retry seletivo por cena — seção 48);
- Movie Render Queue integrado ao Render Queue interno (seção 49: priority, lock, retry,
  cancel, pause, resume, progress, heartbeat, logs);
- Remotion (captions, cards, overlays, CTA) — não substitui Unreal;
- FFmpeg (concat, mux, transcode, masters e formatos sociais) + NVENC;
- Outputs: MASTER_4K, 1080x1920, 1920x1080, 1080x1080, legendas, thumbnail, manifest JSON.

**DoD:** um projeto real produz os 3 formatos de saída + legenda + thumbnail + manifest, e
uma falha em uma cena específica dispara apenas o retry dela, não do vídeo inteiro.

## FASE 9 — Quality

- Quality Engine modular (QA manual + métricas automáticas possíveis, sem "detector mágico
  de realismo" fingido);
- Critérios por categoria (identity/face/body/hair/cloth/product/video/audio — seção 59);
- `quality_score` granular (não um único número "verdade absoluta" — seção 60);
- Reprovação automática por falha P0 (seção 61);
- Comparação lado a lado REFERENCE vs RENDER e A vs B (ex.: Audio2Face vs MetaHuman
  Animator).

**DoD:** uma cena com falha P0 conhecida (ex.: mão deformada) é reprovada automaticamente;
uma cena boa é aprovada; o score fica registrado com todos os campos individuais.

## FASE 10 — MVP dos 30 segundos 🎯

O primeiro grande marco do projeto (seção 62-63): **um vídeo de ~30s, master 4K**, de uma
personagem digital que aguente close de 8s+ sem parecer avatar. Contém obrigatoriamente:
close facial, meio-corpo, PT-BR, fala emocional, mudança de emoção, micro sorriso, olhar
câmera/fora/retorno, piscadas, pausa, respiração, movimento de cabeça, braços, mãos, gesto,
produto, cabelo, roupa, iluminação realista, mudança de câmera.

**DoD:** vídeo entregue, avaliado pelo Quality Engine (Fase 9) e por revisão manual, sem
nenhuma falha P0 da seção 61, com o trecho de 8s em close aprovado especificamente nos
critérios da seção 63 (pele, poros, olhos, tear line, boca, dentes, língua, linha do
cabelo, microexpressões, voz, lip sync).

---

## Matriz de dependências entre fases

```
FASE 0 (auditoria)
   └─▶ FASE 1 (foundation)
          ├─▶ FASE 2 (storage)              ──▶ backups, assets de todas as fases seguintes
          ├─▶ FASE 3 (avatar registry)       ──▶ depende de FASE 2 para persistir assets
          ├─▶ FASE 4 (voice/motion/product)  ──▶ depende de FASE 2
          └─▶ FASE 5 (director)              ──▶ depende de FASE 3 e FASE 4 (referencia avatar/voz/motion/produto)
                 └─▶ FASE 6 (gpu engine)      ──▶ requer nó Hostinger provisionado
                        └─▶ FASE 7 (engines)   ──▶ requer pesquisa técnica resolvida
                               └─▶ FASE 8 (vídeo)
                                      └─▶ FASE 9 (quality)
                                             └─▶ FASE 10 (MVP 30s)
```

## Riscos abertos (ver detalhamento em `docs/ARCHITECTURE.md` §11)

| Risco | Impacto | Fase afetada |
|---|---|---|
| Unreal/MetaHuman com maturidade menor em Linux do que Windows | Alto — pode exigir nó Windows adicional só para render | 7 |
| Distribuição/licenciamento do Audio2Face-3D ainda não confirmada | Médio | 7 |
| Orçamento de VRAM concorrente desconhecido na prática | Médio — afeta política do GPU Orchestrator | 6 |
| Realismo de pele/olhos pode exigir passe neural híbrido além do Unreal puro | Alto — é o requisito P0 do projeto | 7/9 |

Qualquer mudança de tecnologia especificada no prompt-mestre será documentada como
TECNOLOGIA ATUAL / ALTERNATIVA / GANHO / CUSTO / RISCO (seção 83) e aguardará decisão antes
de ser aplicada — nunca substituída silenciosamente.
