# ARCHITECTURE.md — Digital Human Video Factory

> Status deste documento: **v0.2 — FASE 1 (Foundation) concluída · FASE 2 (Storage) implementada**.
> Este documento é vivo. Cada fase implementada deve atualizar as seções relevantes.

---

## 1. Resumo executivo

O **Digital Human Video Factory** é uma plataforma própria para produção **offline** de vídeos
com humanos digitais fotorrealistas (não talking heads, não face swap, não avatar de jogo).

Requisito P0 absoluto: **REALISMO**. Qualidade > velocidade > custo de GPU > quantidade.

Este documento descreve:
- a estrutura final do monorepo;
- a arquitetura funcional (18 domínios);
- os schemas principais das entidades centrais;
- o Provider Pattern usado em toda integração externa;
- o GPU Orchestrator;
- o que depende de RTX 5090, instalação manual, credenciais e pesquisa técnica;
- decisões técnicas tomadas nesta fase e sua justificativa.

Auditoria (FASE 0): o repositório `Marcoslide/CRIADOR-DE-VIDEO` estava **vazio** (sem
nenhum commit, sem branches) no início deste trabalho. Não havia projeto anterior para
preservar — esta é uma implementação greenfield.

---

## 2. Estrutura final do monorepo

Estrutura proposta na seção 9 do prompt-mestre, com um ajuste: o prompt sugere um diretório
raiz `digital-human-factory/`; como o repositório Git já tem nome fixo (`CRIADOR-DE-VIDEO`),
a raiz do monorepo **é a raiz do repositório** — não criamos uma pasta aninhada redundante.

```
CRIADOR-DE-VIDEO/
├── apps/
│   ├── web/                 # React + TypeScript + Vite — dashboard e telas
│   └── api/                 # FastAPI — API HTTP principal
├── core/                    # Domínios de negócio (entidades, regras) — FASE 3+
│   ├── avatars/  voices/  motions/  products/
│   ├── characters/  channels/  projects/  scenes/  quality/
├── services/
│   ├── storage/               # dhf-storage: GoogleDriveStorageProvider — FASE 2 (implementado)
│   └── director/  gpu_orchestrator/  render/  postproduction/  # FASE 5, 6, 8
├── engines/                 # Adapters para motores externos — FASE 7+
│   ├── unreal/  audio2face/  metahuman_animator/
│   ├── voice/  motion/  generative_video/  quality/
├── workers/
│   ├── job_worker/          # Celery worker de jobs gerais — FASE 1 (skeleton real)
│   └── gpu_worker/          # Worker que roda NO nó GPU — FASE 6
├── packages/
│   ├── shared/               # dhf-shared: config, logging, db, celery — FASE 1
│   ├── schemas/               # dhf-schemas: contratos Pydantic compartilhados — FASE 1
│   └── sdk/                  # SDK cliente da API — FASE futura
├── infra/
│   ├── docker/               # Dockerfiles
│   ├── hostinger/            # scripts de provisionamento do nó GPU — FASE 6/7
│   ├── scripts/
│   ├── systemd/               # units para processos do nó GPU — FASE 6/7
│   └── monitoring/            # FASE 6
├── migrations/                # Alembic (schema PostgreSQL), compartilhado por api/worker
├── docs/
├── tests/
├── docker-compose.yml
├── ROADMAP.md
└── README.md
```

### Por que os diretórios `core/`, `engines/`, `infra/hostinger`,
### `infra/systemd`, `infra/monitoring`, `packages/sdk` e `workers/gpu_worker` não existem ainda fisicamente

Regra **ZERO FAKE** (seção 68 do prompt-mestre): não criamos estrutura vazia fingindo
progresso. Cada um desses diretórios nasce **junto com o primeiro código real que o
ocupa**, na fase correspondente (indicada acima e detalhada no `ROADMAP.md`). A árvore
completa já está definida e versionada aqui — é o contrato de onde cada coisa vai morar —
mas só viram pastas no commit da fase que as implementa. `services/storage` foi o primeiro
a nascer (Fase 2); `services/director` e os demais seguem o mesmo padrão nas fases futuras.

### Por que Python "packages" e não apenas pastas soltas

`apps/api`, `workers/job_worker`, `packages/shared` e `packages/schemas` são pacotes Python
instaláveis independentes, organizados como um **workspace `uv`** (um `pyproject.toml` raiz
com `[tool.uv.workspace]`). Isso permite:

- `api` e `job_worker` importarem `dhf-shared` (config, logging, DB, Celery app factory) e
  `dhf-schemas` (contratos Pydantic) sem duplicar código;
- cada serviço ter suas próprias dependências (ex.: `api` não precisa de `celery` instalado
  como dependência direta, `job_worker` não precisa de `fastapi`);
- construir imagens Docker separadas e enxutas por serviço;
- no futuro, extrair qualquer pacote para rodar em outra máquina sem reescrever imports.

Isso é exatamente o requisito da seção 5: *"a arquitetura interna deve permanecer modular
para futuramente separarmos serviços em várias máquinas, mas NÃO introduzir microserviços
desnecessários agora"*. Um workspace continua sendo **um único processo por serviço, rodando
no mesmo nó**, sem HTTP entre eles — só o código é modular.

---

## 3. Arquitetura funcional — os 18 domínios

| # | Domínio | Onde vive | Fase |
|---|---|---|---|
| 1 | Avatar Factory | `core/avatars` + `services/director` (planejamento) | 3 |
| 2 | Avatar Registry | `core/avatars` (entidade `Avatar`) | 3 |
| 3 | Digital Double | `core/avatars` (submódulo `digital_double`) | 3/7 |
| 4 | Face Performance | `engines/audio2face`, `engines/metahuman_animator` | 7 |
| 5 | Voice Bank / Voice DNA | `core/voices` | 4 |
| 6 | Motion Bank / Motion DNA | `core/motions` | 4 |
| 7 | Product Brain | `core/products` | 4 |
| 8 | Product 3D | `core/products` (submódulo `product_3d`) | 4 |
| 9 | Character Brain | `core/characters` | 5 |
| 10 | Channel Brain | `core/channels` | 5 |
| 11 | Director AI | `services/director` | 5 |
| 12 | Scene Engine | `core/scenes` | 5/8 |
| 13 | Unreal / Render Engine | `engines/unreal`, `services/render` | 7/8 |
| 14 | Post Production | `services/postproduction` (Remotion + FFmpeg) | 8 |
| 15 | Quality Engine | `core/quality`, `engines/quality` | 9 |
| 16 | Render Queue | `services/render` + `workers/job_worker` | 8 |
| 17 | Storage Manager | `services/storage` | 2 |
| 18 | GPU Orchestrator | `services/gpu_orchestrator` + `workers/gpu_worker` | 6 |

Cada domínio em `core/` segue o mesmo padrão interno (definido agora, populado a partir da
Fase 3):

```
core/<dominio>/
├── models.py       # SQLAlchemy ORM
├── schemas.py       # Pydantic (request/response), reexportado por packages/schemas quando
│                     # precisa ser consumido por outro serviço
├── repository.py    # acesso a dados
├── service.py        # regras de negócio
└── router.py          # rotas FastAPI, montadas em apps/api
```

---

## 4. Stack e dependências

### 4.1 Backend (Python 3.11)

| Pacote | Uso | Instalado na Fase 1? |
|---|---|---|
| `fastapi` + `uvicorn[standard]` | API HTTP | Sim |
| `pydantic` / `pydantic-settings` | validação, config via `.env` | Sim |
| `sqlalchemy[asyncio]` + `asyncpg` | ORM assíncrono / driver Postgres | Sim |
| `alembic` | migrations | Sim |
| `redis` (redis-py, cliente `asyncio`) | cache/broker | Sim |
| `celery[redis]` | jobs em background | Sim |
| `structlog` | logging estruturado (JSON) | Sim |
| `httpx` | cliente HTTP assíncrono — health checks e, desde a Fase 2, chamadas REST diretas à Google Drive API v3 no `GoogleDriveStorageProvider` | Sim |
| `pytest` / `pytest-asyncio` / `pytest-cov` | testes | Sim (dev) |
| `ruff` | lint/format | Sim (dev) |
| `openai` | Director AI (`OpenAIProvider`) | Fase 5 |
| `anthropic` | Director AI (`AnthropicProvider`, opcional) | Fase 5 |
| `google-auth` | credenciais de service account / OAuth para `GoogleDriveStorageProvider` | Sim (Fase 2) |
| `respx` | mock de `httpx` nos testes unitários do Storage | Sim (Fase 2, dev) |
| `boto3` | `S3StorageProvider` / `R2StorageProvider` (futuro) | Fase futura |
| SDK do provider de voz escolhido (Chatterbox/ElevenLabs) | `VoiceProvider` | Fase 4 |
| `pynvml` / `nvidia-ml-py` | telemetria real de GPU no GPU Orchestrator | Fase 6 |

### 4.2 Frontend (Node 22)

| Pacote | Uso |
|---|---|
| `react` + `react-dom` (v18) | UI |
| `typescript` + `vite` | build/dev server |
| `react-router-dom` | roteamento das ~20 telas |
| `@tanstack/react-query` | data fetching / cache de estado de servidor |
| `tailwindcss` | design system utilitário |
| `lucide-react` | ícones |

### 4.3 Infra

PostgreSQL 16, Redis 7, Docker + Docker Compose, Nginx (build de produção do `web`, fase
posterior), NVIDIA Container Toolkit (Fase 6/7, apenas no nó GPU).

### 4.4 Escolhas técnicas não especificadas no prompt original

O prompt-mestre fixa a stack macro (Python/FastAPI, React, PostgreSQL, Redis, Celery,
Docker). As ferramentas abaixo são detalhes de implementação dentro dessa stack — não
substituem nenhuma tecnologia que o prompt tenha especificado, por isso não passam pelo
gate da seção 83 (que se aplica a *trocar* algo já decidido). Listadas aqui por
transparência:

| Escolha | Alternativa considerada | Motivo |
|---|---|---|
| `uv` (workspace + gerenciador de pacotes) | `poetry`, `pip` + `requirements.txt` | Workspaces nativos (múltiplos pacotes, um lockfile), muito mais rápido, padrão emergente em 2025 |
| `structlog` | `logging` puro + formatter JSON manual | Logging estruturado (seção 70) de forma nativa, sem reinventar |
| Vite | Create React App (descontinuado), Next.js | V1 é SPA pura consumindo a API; Next.js traria SSR/roteamento server-side desnecessário agora |
| Tailwind CSS | CSS-in-JS, Material UI, Ant Design | Controle visual fino para um "produto premium" (seção 75) sem herdar estética de biblioteca de componentes genérica |
| TanStack Query | Redux, SWR | Cache/estado de servidor (status de GPU, filas, jobs) é o padrão de dados dominante nesta UI |
| REST direto via `httpx` (Drive API v3) | `google-api-python-client` | O cliente oficial é síncrono (exigiria `run_in_threadpool` em toda chamada, numa app 100% assíncrona) e usa geração dinâmica de métodos via discovery document, dificultando tipagem e streaming real de upload/download. REST direto com `httpx.AsyncClient` dá controle nativo sobre upload resumable e download em chunks, e mantém o mesmo cliente HTTP já usado nos health checks. `google-auth` continua sendo usado — só para obter/renovar o token, não para chamar a API |

Nenhuma dessas escolhas é definitiva a ponto de travar o projeto — todas são isoladas e
substituíveis sem reescrever domínio, seguindo o Provider Pattern (seção 67) e a separação
de camadas.

---

## 5. Provider Pattern

Toda integração externa (seção 67) é acessada através de uma interface abstrata definida em
`core/<dominio>/providers.py` ou `services/<servico>/providers.py`, nunca chamada
diretamente do código de negócio. Interfaces previstas:

```python
class StorageProvider(Protocol):
    async def get_status(self, *, force_refresh: bool = False) -> StorageStatus: ...
    async def upload(self, local_path: str, remote_path: str) -> StorageManifestEntry: ...
    async def download(self, remote_path: str, local_path: str) -> None: ...
    async def exists(self, remote_path: str) -> bool: ...
    async def delete(self, remote_path: str, *, allow_permanent: bool = False) -> None: ...
    async def list(self, prefix: str) -> list[StorageManifestEntry]: ...
    async def move(self, src: str, dst: str) -> None: ...
    async def copy(self, src: str, dst: str) -> None: ...
    async def get_metadata(self, remote_path: str) -> StorageManifestEntry: ...
    async def sync(self, local_dir: str, remote_dir: str) -> SyncReport: ...

class AIProvider(Protocol):
    async def plan_scenes(self, request: DirectorRequest) -> ScenePlan: ...

class VoiceProvider(Protocol):
    async def synthesize(self, text: str, voice: VoiceProfile, style: VoicePerformance) -> AudioAsset: ...

class FacialPerformanceProvider(Protocol):
    async def generate(self, audio: AudioAsset, avatar: Avatar, emotion: EmotionTrack) -> FacePerformanceAsset: ...

class UnrealEngineProvider(Protocol):
    def load_avatar(self, avatar: Avatar) -> None: ...
    def load_environment(self, scene: Scene) -> None: ...
    def load_product(self, product: Product) -> None: ...
    def apply_motion(self, motion: Motion) -> None: ...
    def apply_face_animation(self, face_performance: FacePerformanceAsset) -> None: ...
    def configure_camera(self, camera: CameraSpec) -> None: ...
    def configure_lighting(self, lighting: LightingSpec) -> None: ...
    def create_sequence(self, scene: Scene) -> SequenceHandle: ...
    def render_scene(self, sequence: SequenceHandle) -> RenderResult: ...
    def render_project(self, project: VideoProject) -> list[RenderResult]: ...

class QualityProvider(Protocol):
    async def evaluate(self, render: RenderResult) -> QualityScore: ...

class GenerativeVideoProvider(Protocol):
    async def generate(self, spec: GenerativeVideoSpec) -> RenderResult: ...
```

Implementações concretas (`GoogleDriveStorageProvider`, `OpenAIProvider`,
`ChatterboxProvider`, `ElevenLabsProvider`, `Audio2FaceProvider`,
`MetaHumanAnimatorProvider` etc.) entram fase a fase — ver `ROADMAP.md`.

Cada Provider expõe um `status` obrigatório, seguindo a enumeração da seção 68 — nunca um
booleano "conectado" fake:

```python
class ProviderStatus(str, Enum):
    REAL = "real"                   # integração real, testada, funcionando
    DEVELOPMENT = "development"      # integração real em progresso, com limitações conhecidas
    MOCK = "mock"                    # implementação simulada, só permitida em teste/dev
    NOT_CONFIGURED = "not_configured"  # credencial/config ausente
    NOT_INSTALLED = "not_installed"    # dependência externa (ex.: Unreal, Audio2Face) não instalada
    ERROR = "error"                    # falhou ao inicializar/chamar
```

A UI (seção 68/69) **sempre** reflete esse status real — nunca mostra "Connected ✅" para
algo `NOT_CONFIGURED`/`NOT_INSTALLED`, nunca gera um MP4 placeholder fingindo render.

---

## 6. Schemas principais (design — implementação a partir da Fase 3)

Notação Pydantic/SQLAlchemy simplificada, campos essenciais (a seção 12 e seguintes do
prompt-mestre têm a lista completa; aqui consolidamos o modelo de dados).

### Storage (seção 6 — implementado na Fase 2, `packages/schemas/dhf_schemas/storage.py`)

Único bloco desta seção que já é código real, não apenas design — os demais schemas deste
capítulo continuam como contrato para a Fase 3+.

```python
class StorageConnectionStatus(str, Enum):
    NOT_CONFIGURED = "not_configured"  # nenhuma credencial configurada/carregável
    CONNECTING = "connecting"          # refresh de status em andamento (transitório)
    CONNECTED = "connected"            # autenticado, raiz acessível, árvore oficial completa
    DEGRADED = "degraded"              # autenticado e acessível, mas árvore incompleta/inesperada
    ERROR = "error"                    # credencial presente mas falhou autenticação/chamada

class TreeValidationResult(BaseModel):
    expected: list[str]
    found: list[str]
    missing: list[str]
    unexpected: list[str]              # pastas extras na raiz, fora da lista oficial — não é erro, só informativo
    valid: bool                        # True apenas se `missing` estiver vazio

class StorageStatus(BaseModel):
    status: StorageConnectionStatus
    detail: str | None
    root_folder_id: str | None
    tree: TreeValidationResult | None
    checked_at: datetime

class StorageManifestEntry(BaseModel):
    remote_path: str            # caminho lógico ex.: "03_AVATAR_IDENTITY_FOTOS/lia/v1/head360/000.png"
    provider_id: str            # ID nativo do provider (Drive file id)
    size_bytes: int
    mime_type: str
    checksum: str | None        # md5Checksum do Drive quando disponível
    version: str | None         # convenção de versão do caller (ex.: "v1"), não imposta pelo provider
    modified_at: datetime
    web_view_url: str | None

class SyncReport(BaseModel):
    uploaded: list[str]
    skipped_unchanged: list[str]
    failed: list[tuple[str, str]]      # (caminho, motivo)
    duration_s: float
```

`StorageProvider` (Protocol, seção 5 acima) é a interface; `GoogleDriveStorageProvider`
(`services/storage`) é a única implementação até aqui. Detalhes de configuração, a árvore
oficial de 18 pastas e a convenção de caminhos/versão estão em
`docs/STORAGE_GOOGLE_DRIVE.md`.

### Avatar (seção 12)

```python
class AvatarStatus(str, Enum):
    DRAFT = "draft"
    IDENTITY_LOCKED = "identity_locked"
    MULTIVIEW_IN_PROGRESS = "multiview_in_progress"
    MULTIVIEW_APPROVED = "multiview_approved"
    MESH_IN_PROGRESS = "mesh_in_progress"
    MESH_APPROVED = "mesh_approved"
    RIGGED = "rigged"
    MATERIALS_APPROVED = "materials_approved"
    FACE_APPROVED = "face_approved"
    VOICE_APPROVED = "voice_approved"
    MOTION_APPROVED = "motion_approved"
    MASTER_APPROVED = "master_approved"
    PRODUCTION_READY = "production_ready"   # único status que libera produção automática

class Avatar(BaseModel):
    avatar_id: UUID
    name: str
    slug: str
    version: int
    status: AvatarStatus
    master_reference: StorageManifestEntry
    identity_profile: IdentityProfile        # seção 13 — bloqueado após IDENTITY_LOCKED
    visual_profile: VisualProfile
    voice_profile_id: UUID | None
    motion_profile_id: UUID | None
    character_profile_id: UUID | None
    digital_double_manifest: DigitalDoubleManifest | None
    storage_manifest: StorageManifest
    quality_score: QualityScore | None
    created_at: datetime
    updated_at: datetime
```

### AvatarAsset — referências 360°/detalhe (seções 14-15)

```python
class AvatarAsset(BaseModel):
    asset_id: UUID
    avatar_id: UUID
    version: int
    category: Literal["head360", "halfbody360", "fullbody360", "eyes", "ears", "skin",
                       "mouth", "teeth", "tongue", "hair", "hands", "feet", "expressions"]
    angle: int | None          # 0-350, passo de 10, quando aplicável
    elevation: float | None
    pose: str | None
    expression: str | None
    resolution: str
    storage_uri: str
    approved: bool
    quality_score: float | None
    notes: str | None
```

### Voice / VoiceProfile (seções 27-31)

```python
class Voice(BaseModel):
    voice_id: UUID
    name: str
    language: str
    accent: str | None
    provider: str                     # "chatterbox" | "elevenlabs" | ...
    model: str
    reference_assets: list[StorageManifestEntry]
    consent: ConsentRecord             # obrigatório — sem consentimento não é usável
    license: str
    style: str
    energy: float
    pace: float
    quality_score: float | None
    status: Literal["draft", "approved"]

class VoicePerformance(BaseModel):
    preset: Literal["neutral", "conversation", "sales", "storytelling", "energetic",
                     "intimate", "serious", "happy", "surprised", "empathetic"]
    emotion: str
    energy: float
    pace: float
    pauses: list[PauseMarker]
    nonverbal_events: list[Literal["breath", "laugh", "small_laugh", "hmm", "pause",
                                     "reaction", "whisper", "surprise"]]
```

### Motion / MotionDNA (seções 32-35)

```python
class Motion(BaseModel):
    motion_id: UUID
    name: str
    family: Literal["IDLE", "EXPLAIN", "EMPHASIS", "POINT", "REACTION",
                     "PRODUCT_INTERACTION", "TURN", "WALK", "SIT", "STAND",
                     "BREATHING", "MICRO_MOVEMENT", "TRANSITION"]
    duration: float
    energy: float
    body_parts: list[str]
    tags: list[str]
    source: Literal["mocap_human", "generative", "hybrid"]
    license: str
    quality_score: float | None
    compatible_rigs: list[str]
    storage_uri: str

class MotionDNA(BaseModel):
    avatar_id: UUID
    gesture_frequency: float
    gesture_amplitude: float
    head_activity: float
    eye_contact: float
    smile_frequency: float
    posture: str
    energy: float
    walking_style: str
    dominant_hand: Literal["left", "right"]
    reaction_style: str
    personal_space: float
```

### Product / Product3D (seções 36-38)

```python
class ProductFactClass(str, Enum):
    CONFIRMED_FACT = "confirmed_fact"
    AI_ARGUMENT = "ai_argument"
    INFERENCE = "inference"
    PROHIBITED_CLAIM = "prohibited_claim"      # nunca falado pelo Director

class Product(BaseModel):
    product_id: UUID
    sku: str
    title: str
    description: str
    images: list[StorageManifestEntry]
    confirmed_facts: list[str]
    benefits: list[str]
    dimensions: Dimensions
    weight: float
    variants: list[ProductVariant]
    price: Money
    faq: list[FAQEntry]
    objections: list[str]
    sales_arguments: list[str]
    prohibited_claims: list[str]

class Product3D(BaseModel):
    product_id: UUID
    mesh: StorageManifestEntry | None
    textures: list[StorageManifestEntry]
    materials: list[MaterialSpec]
    dimensions: Dimensions
    weight: float
    center_of_mass: Vector3
    collision: CollisionSpec | None
    grip_points: list[Vector3]
    presentation_points: list[Vector3]
    parametric: bool           # True para produtos simples sem mesh dedicado
```

### Character / Channel (seções 39-40)

```python
class CharacterBrain(BaseModel):
    character_id: UUID
    avatar_id: UUID
    personality: str
    speaking_style: str
    humor: float
    energy: float
    behavior_rules: list[str]
    allowed_topics: list[str]
    restricted_topics: list[str]
    history: list[str]
    memories: list[str]
    preferences: dict[str, str]

class Channel(BaseModel):
    channel_id: UUID
    avatar_id: UUID
    name: str
    platform: str
    niche: str
    audience: str
    objectives: list[str]
    content_pillars: list[str]
    tone: str
    history: list[str]
    strategy: str
```

### Scene Plan (seção 43) e Video Project (seção 45)

```python
class Scene(BaseModel):
    scene_id: UUID
    speech: str
    voice_style: VoicePerformance
    emotion: str
    emotion_intensity: float
    gaze_target: Literal["CAMERA", "PRODUCT", "OBJECT", "LEFT", "RIGHT", "UP", "DOWN", "CUSTOM"]
    blink_profile: BlinkProfile
    facial_expression: str
    head_motion: str
    breathing: str
    gesture: str | None
    body_action: str | None
    motion_id: UUID | None
    product_action: str | None
    product_id: UUID | None
    camera: CameraSpec
    lens: str
    camera_motion: str
    lighting: LightingSpec
    environment: str
    overlay: list[OverlaySpec]
    music: str | None
    sound_effects: list[str]
    duration: float
    transition: str
    status: Literal["pending", "rendering", "rendered", "failed"]
    render_path: str | None
    quality_score: QualityScore | None
    retry_count: int = 0

class VideoProjectStatus(str, Enum):
    DRAFT = "draft"; DIRECTING = "directing"; READY = "ready"
    VOICE_PROCESSING = "voice_processing"; FACE_PROCESSING = "face_processing"
    MOTION_PROCESSING = "motion_processing"; SCENE_BUILDING = "scene_building"
    RENDERING = "rendering"; POST_PROCESSING = "post_processing"
    QUALITY_CHECK = "quality_check"; QUALITY_FAILED = "quality_failed"
    APPROVED = "approved"; COMPLETED = "completed"; FAILED = "failed"

class VideoProject(BaseModel):
    project_id: UUID
    avatar_id: UUID
    channel_id: UUID
    product_ids: list[UUID]
    topic: str
    objective: str
    duration: float
    aspect_ratio: str
    resolution: str
    quality_preset: str
    scene_plan: list[Scene]
    status: VideoProjectStatus
    render_cost: CostRecord
    gpu_time: float
    quality_score: QualityScore | None
    created_at: datetime
```

### QualityScore (seções 58-61)

```python
class QualityScore(BaseModel):
    identity_score: float
    face_score: float
    voice_score: float
    motion_score: float
    hands_score: float
    hair_score: float
    product_score: float
    lighting_score: float
    temporal_score: float
    overall_score: float
    p0_failures: list[str]        # qualquer item aqui reprova a cena, independente da média
    evaluated_at: datetime
    evaluator: Literal["manual", "automatic", "hybrid"]
```

### GPU State (seção 50)

```python
class GPUState(BaseModel):
    gpu_model: str
    driver: str
    cuda_version: str
    vram_total_mb: int
    vram_used_mb: int
    temperature_c: float
    power_w: float
    utilization_pct: float
    nvenc_utilization_pct: float
    cpu_usage_pct: float
    ram_usage_pct: float
    disk_usage_pct: float
    resident_models: list[ModelHandle]
    active_job: JobHandle | None
    recorded_at: datetime
```

Estes schemas **não são implementados como tabelas na Fase 1** (ver `ROADMAP.md`, Fase 3+).
Aqui eles são o contrato acordado; a Fase 1 implementa apenas a fundação de infraestrutura
que os vai sustentar (config, DB, logging, filas, health checks).

---

## 7. GPU Orchestrator (design conceitual — implementação na Fase 6)

Roda como processo próprio (`services/gpu_orchestrator`) no nó Hostinger, e é o único
componente autorizado a carregar/descarregar modelos na VRAM. Conceitos-chave:

- **HOT / WARM / UNLOADED** — três estados de residência de modelo (seção 51). Nenhum
  modelo fica "sempre carregado" por padrão; o Orchestrator decide com base em fila e
  prioridade.
- **Admissão de job**: antes de iniciar uma etapa, o Orchestrator verifica VRAM livre
  necessária vs. modelos residentes; descarrega o modelo de menor prioridade se preciso
  (nunca deixa a VRAM saturar a ponto de OOM).
- **Telemetria real** via `pynvml`/`nvidia-smi` — nunca um número simulado.
- **Batch por avatar** (seção 52): a fila de render agrupa jobs do mesmo avatar para
  reaproveitar mesh/materials/groom/rig/shaders/voice/motion cache já residentes.
- **CPU pipeline** (seção 53): enquanto a GPU renderiza uma cena, os 32 cores da CPU
  preparam a próxima (sync de assets, metadata, Remotion, áudio, upload).

Interface preliminar:

```python
class GPUOrchestrator(Protocol):
    async def get_state(self) -> GPUState: ...
    async def request_model(self, model: ModelHandle, priority: int) -> ModelResidency: ...
    async def release_model(self, model: ModelHandle) -> None: ...
    async def schedule_job(self, job: JobHandle) -> None: ...
    async def next_job(self) -> JobHandle | None: ...
```

Esta interface **não é implementável de verdade sem uma RTX 5090 real** — ver seção 9
abaixo. Na Fase 1 ela existe apenas como documentação.

---

## 8. O que depende da RTX 5090 (nó Hostinger)

Nada disto roda neste ambiente de desenvolvimento (sem GPU) nem em CI comum — só no nó
Hostinger com a RTX 5090 física:

- GPU Orchestrator (telemetria real de VRAM/temperatura/power/NVENC via `nvidia-smi`/`pynvml`);
- `workers/gpu_worker` (execução de jobs de GPU);
- Audio2Face-3D (inferência);
- MetaHuman Animator (quando processado localmente);
- Unreal Engine — render de cena (Movie Render Queue), Sequencer;
- Modelos generativos de vídeo/upscalers;
- Inferência local de voz, se o provider de voz escolhido rodar on-prem (ex.: Chatterbox
  self-hosted);
- Encode via NVENC;
- Modelos de Quality Engine baseados em GPU (se vierem a existir).

Estratégia: todo esse código é escrito e testado com **contrato de interface** (Provider
Pattern) e testes unitários com mocks explicitamente marcados `MOCK`; a validação real só
acontece quando o nó Hostinger estiver provisionado (Fase 6+), reportando `NOT_INSTALLED`
até lá — nunca simulando sucesso.

## 9. O que depende de instalação manual (não automatizável via `pip`/`npm`/Docker puro)

- **Unreal Engine 5** + plugin MetaHuman + Movie Render Queue — instalação/licença própria;
  a seção 11 do prompt-mestre já orienta não forçar Unreal para dentro de Docker se isso
  prejudicar estabilidade;
- Driver NVIDIA + CUDA + cuDNN + TensorRT no Ubuntu 24.04 do nó Hostinger;
- NVIDIA Omniverse / Audio2Face (instalação e, possivelmente, licenciamento próprio);
- NVIDIA Container Toolkit (para os containers que precisarem de CUDA);
- `ffmpeg` compilado/instalado com suporte a NVENC no nó GPU;
- Ferramenta de reconstrução 3D/fotogrametria (a escolher — ver seção 12 "pesquisa
  técnica");
- `rclone` ou equivalente, se optarmos por sync de baixo nível complementar ao
  `GoogleDriveStorageProvider`.

## 10. O que depende de credenciais (nenhuma incluída neste repositório)

| Credencial | Usada por | Fase |
|---|---|---|
| `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` (conteúdo) ou `GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE` (caminho) | `GoogleDriveStorageProvider` | 2 — **ainda não fornecida**; provider reporta `NOT_CONFIGURED` até então |
| `OPENAI_API_KEY` | `OpenAIProvider` (Director AI) | 5 |
| `ANTHROPIC_API_KEY` (opcional) | `AnthropicProvider` (Director AI) | 5 |
| `ELEVENLABS_API_KEY` | `ElevenLabsProvider` | 4 |
| Credenciais do provider Chatterbox (se hospedado) | `ChatterboxProvider` | 4 |
| `POSTGRES_PASSWORD`, `REDIS_PASSWORD` (produção) | infra | 1 (dev usa defaults locais) |
| SSH/API do nó Hostinger | deploy/infra scripts | 6 |
| Licença NVIDIA Omniverse/Audio2Face, se aplicável | Face Performance | 7 |
| `S3`/`R2` access keys (se/quando adotado) | `S3StorageProvider`/`R2StorageProvider` | futura |

Nenhuma dessas chaves existe nos arquivos do projeto. `.env.example` documenta os nomes das
variáveis; `.env` real fica fora do Git (ver `.gitignore` e `docs/SECURITY.md`, a escrever
na Fase de segurança).

## 11. O que ainda precisa de pesquisa técnica

1. **Unreal Engine + MetaHuman no Linux (Ubuntu 24.04).** A automação via linha de
   comando/Python do Unreal e o pipeline MetaHuman Animator são historicamente mais maduros
   no Windows. Isso é uma tensão real entre duas decisões já aprovadas (SO Ubuntu 24.04 na
   seção 5, e Unreal/MetaHuman como tecnologia central na seção 17) que precisa de
   investigação dedicada antes da Fase 7 — inclui validar Movie Render Queue headless em
   Linux, drivers gráficos com GPU também usada para compute, e se será necessário rodar o
   Unreal via Windows em outra máquina/VM só para essa etapa.
2. **Pipeline de reconstrução 3D**: qual ferramenta leva de referências 360° a uma mesh
   master de qualidade suficiente para virar MetaHuman customizada (fotogrametria clássica
   vs. reconstrução neural/Gaussian Splatting) e qual o caminho exato de import para "custom
   mesh → MetaHuman" na versão de Unreal que usaremos.
3. **Audio2Face-3D**: modelo de distribuição atual (microserviço local via NIM/container vs.
   nuvem), requisitos de licença, e superfície de API para chamadas automatizadas
   headless.
4. **MetaHuman Animator**: requisitos de captura (iPhone ARKit vs. HMC estéreo) e
   viabilidade operacional para esta equipe.
5. **Benchmark de voz**: metodologia objetiva para comparar Chatterbox vs. ElevenLabs em
   realismo (não assumir "grátis é melhor" nem "pago é melhor" — seção 28), e suporte de
   cada um aos eventos não-verbais da seção 30.
6. **Orçamento real de VRAM concorrente**: quanto cada engine consome simultaneamente
   (Unreal+MetaHuman, Audio2Face, TTS, upscaler) nos 32 GB da RTX 5090, para o GPU
   Orchestrator definir política de admissão/despejo com dados reais, não estimativas.
7. **Fallback de renderização neural**: se o caminho puramente Unreal não atingir o nível de
   realismo de pele/olhos exigido (P0), avaliar um passe híbrido de refinamento neural
   pós-render.

Nenhum destes pontos bloqueia a Fase 1. Eles bloqueiam, nesta ordem, as Fases 6 e 7.

---

## 12. Observabilidade e auditoria (fundação criada na Fase 1, consumida a partir da Fase 3)

- **Structured logging** (`packages/shared/dhf_shared/logging.py`, `structlog` → JSON):
  campos padrão `timestamp`, `level`, `service`, `event`; campos contextuais
  `project_id`, `scene_id`, `avatar_id`, `job_id`, `provider`, `gpu`, `stage`, `duration`,
  `status`, `error`, `vram`, `cost` são anexados via `bind()` quando essas entidades
  existirem (Fase 3+).
- **Audit log** (seção 71) e **cost tracking** (seção 72): tabelas dedicadas, adicionadas
  quando os eventos que elas registram passarem a existir (aprovação de avatar, troca de
  provider, render gerado etc.) — Fase 3+.

## 13. Segurança (fundação)

- Segredos exclusivamente via variáveis de ambiente (`.env`, nunca commitado — só
  `.env.example` com placeholders, marcado como "dev only", nunca copiado direto para
  produção — ver aviso no topo do próprio arquivo);
- `.gitignore` cobre `.env`, artefatos de build, caches, binários de modelo;
- Sem chave de API no frontend: o `web` nunca fala diretamente com OpenAI/ElevenLabs/Drive —
  sempre via `api`.
- **Sanitização de erros em endpoints públicos** (`dhf_shared.errors.sanitize_error`):
  `/health*` e `/storage/status` nunca devolvem `str(exc)`, URL interna, host/porta ou
  stack trace — só um `error_code` + mensagem genérica classificados pelo tipo da exceção.
  O erro completo continua indo para o log estruturado (`dhf_shared.logging`), nunca para
  o cliente HTTP.
- **`docker-compose.yml` (base) nunca publica porta de PostgreSQL/Redis** e recusa subir
  sem `POSTGRES_USER`/`PASSWORD`/`DB` explícitos (`${VAR:?...}`) — dev ganha conveniência
  (porta em `127.0.0.1`, senha padrão) só via `docker-compose.override.yml`, carregado
  automaticamente por `docker compose up` mas nunca usado em produção
  (`docker-compose.prod.yml`, uso explícito com `-f`). Limitação conhecida: o guard
  `${VAR:?...}` detecta variável *ausente*, não "ainda com o valor de exemplo copiado" —
  ver aviso em `.env.example`.
- `docs/SECURITY.md` completo é entregável de uma fase própria (seção 77), não da Fase 1.
