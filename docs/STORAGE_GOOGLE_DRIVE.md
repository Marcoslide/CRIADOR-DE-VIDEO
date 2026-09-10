# STORAGE_GOOGLE_DRIVE.md — Digital Human Video Factory

> Status: **Fase 2 — código completo, validação real com credencial pendente.**
> Implementação: `services/storage` (`dhf_storage`). Interface: `packages/schemas/dhf_schemas/storage.py`.

---

## 1. Visão geral

O Google Drive é a **fonte definitiva** dos ativos do projeto (seção 6 do prompt-mestre) —
o SSD do nó Hostinger é hot storage/cache/scratch, nunca a fonte de verdade.
`GoogleDriveStorageProvider` é a única implementação de `StorageProvider` até aqui, feita
sobre chamadas REST diretas à Drive API v3 (`httpx` assíncrono), autenticando com uma
service account via `google-auth`.

**Regra que este provider nunca quebra:** sem uma credencial válida, todo `get_status()`
retorna `NOT_CONFIGURED` — nunca finge estar conectado. Qualquer outra operação
(`upload`, `download`, ...) chamada sem credencial levanta `StorageNotConfiguredError`
explicitamente, nunca falha silenciosa ou sucesso falso.

## 2. Árvore oficial de pastas

Criada **manualmente** pelo usuário no Google Drive — o provider nunca cria, renomeia ou
apaga estas 18 pastas de topo, só as descobre por nome e valida que existem.

Pasta raiz **"CRIADOR DE VIDEO"**:
[`13BTUf5Oyp8fb_CT2H0OJ6LeuZKzm3pxE`](https://drive.google.com/drive/folders/13BTUf5Oyp8fb_CT2H0OJ6LeuZKzm3pxE)

```
00_PROJETO_GOVERNANCA
01_INFRA
02_SISTEMA_STORAGE
03_AVATAR_IDENTITY_FOTOS
04_DIGITAL_DOUBLE_MESH_RIG
05_REALISMO_LOOKDEV
06_FACE_PERFORMANCE
07_VOICE_DNA
08_MOTION_DNA_CORPO_MAOS
09_PRODUTO_PRODUCT_3D
10_DIRECTOR_AI_BRAINS
11_CENARIOS_CAMERA_LUZ
12_VIDEO_PIPELINE_UNREAL_RENDER
13_EDICAO_REMOTION_FFMPEG
14_QUALITY_GATE_TESTES
15_MVP_VIDEO_30S
16_ESCALA_CANAIS_ARTISTAS
17_FUTURO_LIVE
```

Lista canônica em código: `services/storage/dhf_storage/tree.py:OFFICIAL_TOP_LEVEL_FOLDERS`.

### Convenção de caminho (`remote_path`)

Todo método do provider recebe caminhos POSIX relativos à raiz, ex.:

```
03_AVATAR_IDENTITY_FOTOS/lia/v1/head360/000.png
07_VOICE_DNA/lia/v3/reference_01.wav
02_SISTEMA_STORAGE/_tmp/teste-integracao-2026-09-10.bin
```

- **1º segmento**: obrigatoriamente um dos 18 nomes oficiais acima — só descoberto, nunca
  criado. Qualquer outro nome levanta `ValueError` imediatamente.
- **Segmentos seguintes (pastas)**: descobertos e **criados idempotentemente** sob demanda
  (`create_missing=True` em upload/sync; `False` em list/exists/download/get_metadata —
  operações de leitura nunca criam pasta como efeito colateral).
- **Convenção de versão**: o provider não impõe nada — `v1`, `v2`, ... é só mais um
  segmento de caminho, a cargo de quem chama (Avatar Registry, Voice Bank, ... a partir da
  Fase 3). `StorageManifestEntry.version` fica disponível para o caller preencher.

### Área de scratch (`02_SISTEMA_STORAGE/_tmp/`)

Único lugar onde `delete()` sem `allow_permanent=True` tem efeito — e mesmo ali, move para
a lixeira do Drive (recuperável), nunca exclusão definitiva. Usada pelos testes de
integração para criar/apagar um arquivo de verdade sem risco de tocar ativos permanentes.

## 3. Estados de conexão

```
NOT_CONFIGURED   nenhuma credencial configurada/carregável — caminho normal em dev
CONNECTING       um refresh de status já está em andamento (outra requisição concorrente)
CONNECTED        autenticado, raiz acessível, as 18 pastas oficiais foram encontradas
DEGRADED         autenticado e acessível, mas falta alguma das 18 pastas oficiais
ERROR            credencial presente mas autenticação ou chamada à API falhou
```

`get_status(force_refresh=False)` cacheia o resultado por
`GOOGLE_DRIVE_STATUS_CACHE_TTL_S` segundos (default 30s) para não bater na Drive API a
cada poll do dashboard; `force_refresh=true` ignora o cache.

## 4. Configuração (variáveis de ambiente)

Ver `.env.example` para a lista completa com comentários. Resumo:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `GOOGLE_DRIVE_ROOT_FOLDER_ID` | Não (tem default = pasta oficial) | ID da pasta raiz |
| `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` | Uma das duas | Conteúdo do JSON da service account |
| `GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE` | Uma das duas | Caminho local para o arquivo `.json` |
| `GOOGLE_DRIVE_REQUEST_TIMEOUT_S` | Não | Timeout por request HTTP (default 30s) |
| `GOOGLE_DRIVE_UPLOAD_CHUNK_SIZE_BYTES` / `..._DOWNLOAD_...` | Não | Tamanho do chunk de streaming (default 8 MiB) |
| `GOOGLE_DRIVE_MAX_RETRIES` | Não | Tentativas em erro transitório (default 5) |
| `GOOGLE_DRIVE_RETRY_BASE_DELAY_S` | Não | Base do backoff exponencial (default 1s) |
| `GOOGLE_DRIVE_STATUS_CACHE_TTL_S` | Não | TTL do cache de status (default 30s) |

**Produção (nó Hostinger): service account, nunca OAuth de usuário** — execução headless
não tem navegador para completar um fluxo OAuth interativo. `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`
via secret do ambiente é o caminho recomendado (não grava a chave em disco no container).
`GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE` é conveniente para dev local.

A service account precisa ter sido **compartilhada como colaboradora** da pasta raiz
"CRIADOR DE VIDEO" no Drive (uma service account não tem storage próprio — só enxerga o
que foi explicitamente compartilhado com o e-mail dela).

### Segurança

- O conteúdo da credencial e o access token **nunca** aparecem em log — só o
  "acontecimento" (`storage.credential_load_error` etc.) e mensagens de erro genéricas.
- `.env` nunca é commitado (`.gitignore`); só `.env.example` com placeholders.
- Sem chave no frontend: o `web` nunca fala com o Drive diretamente, sempre via `api`.

## 5. Streaming e retry

- **Upload**: sessão resumable de upload (`uploadType=resumable`); o arquivo local é lido
  em chunks (`aiofiles`) e enviado num único PUT com o corpo em streaming — nunca carrega o
  arquivo inteiro em memória. **Limitação conhecida**: não implementa retomada parcial após
  falha a meio da transferência (isso exigiria o protocolo completo de resumable upload em
  múltiplos PUTs com `Content-Range`); se o PUT falhar, o `with_retry` reenvia a tentativa
  inteira, não só o pedaço que faltava.
- **Download**: `GET .../files/{id}?alt=media`, resposta consumida via `client.stream(...)`
  e gravada em disco em chunks. Se falhar no meio, o arquivo local parcial é removido antes
  de propagar o erro — nunca deixa um arquivo corrompido para trás se passando por sucesso.
- **Upload que já existe**: se já existe um arquivo com aquele nome na pasta de destino, o
  provider faz `PATCH` (atualiza o conteúdo do arquivo existente) em vez de `POST` (criar
  novo) — evita duplicar arquivos com o mesmo nome ao re-subir o mesmo `remote_path`.
- **Retry**: só em `429` (quota) e `5xx`/erro de transporte, com backoff exponencial +
  jitter, até `GOOGLE_DRIVE_MAX_RETRIES` tentativas. Qualquer outro código (`404`, `401`,
  `403` fora de rate limit) propaga na primeira tentativa — nunca retry cego.

## 6. Uso

### Do código (outro serviço, a partir da Fase 3+)

```python
from dhf_storage.factory import get_storage_provider

provider = get_storage_provider()
entry = await provider.upload("/tmp/000.png", "03_AVATAR_IDENTITY_FOTOS/lia/v1/head360/000.png")
```

Consumidores só precisam depender de `dhf_schemas.storage.StorageProvider` (a interface) —
nunca de `dhf_storage` diretamente, exceto quem efetivamente compõe/injeta o provider
(hoje, só `apps/api`).

### Endpoint HTTP

```
GET /storage/status               # cacheado (até 30s por padrão)
GET /storage/status?force_refresh=true
```

### CLI

```bash
uv run --project services/storage dhf-storage check
# ou
uv run --project services/storage python -m dhf_storage check
```

Saída: status, `root_folder_id`, e a árvore (pastas encontradas/faltando/inesperadas).
Exit code `0` só quando `status == connected`; `1` em qualquer outro caso — pensado para
uso em script/CI (ex.: gate de deploy no nó Hostinger).

## 7. O que ainda não existe

- Rotina de **backup do PostgreSQL para o Drive** (seção 65 do prompt-mestre) — planejada
  para a Fase 2 no `ROADMAP.md` original, mas fora do escopo do card que implementou este
  provider; ainda não construída.
- `S3StorageProvider` / `R2StorageProvider` — adapters futuros atrás da mesma interface
  `StorageProvider`, sem necessidade de tocar em quem já consome o provider.
- Validação real contra o Drive de produção — ver `docs/ARCHITECTURE.md` §10: nenhuma
  credencial foi fornecida ainda para esta implementação. Testes de integração reais
  (`tests/storage/test_google_drive_integration.py`) existem e são corretos, mas ficam
  `SKIPPED` até uma `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`/`_FILE` real ser configurada.
