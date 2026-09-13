# Avatar Factory Control Plane

> Evolui o Avatar Registry (`core/avatars`, PR #1) com os subsistemas que a fundação
> deixou explicitamente para depois: Identity Lock, captura de referências 360°/
> especializadas, QA determinístico, quality gates com enforcement real e histórico
> imutável de transição de status. **Realismo é P0**: nada aqui gera mesh, textura,
> rig ou vídeo — isso depende da RTX 4090 real (`infra/gpu/`, PR #4) e fica
> honestamente `NOT_GENERATED`/`BLOCKED` até lá. Zero mock: toda checagem é real.

## Por que um pacote novo, não uma extensão de `dhf_avatars`

`core/avatars/dhf_avatars` continua **inalterado** por esta missão — `AvatarStatus`,
`ALLOWED_STATUS_TRANSITIONS` e o `PATCH /avatars/{id}` genérico (usado pela tela
`Avatars.tsx` para um avanço manual/administrativo, sem gate) já existiam e seguem
funcionando exatamente como antes. Os subsistemas novos vivem em
`core/avatar_factory/dhf_avatar_factory` — um domínio separado que **depende** de
`dhf-avatars` (para `AvatarRecord`/`AvatarStatus`), `dhf-storage` e `dhf-schemas`
(para `StorageProvider`), mas nunca os modifica. Isso segue o padrão de camadas já
estabelecido (`docs/ARCHITECTURE.md` §4) e evita qualquer risco de regressão nos
testes/contratos que Codex e outras sessões já dependem.

## Arquitetura

```
core/avatar_factory/dhf_avatar_factory/
  enums.py              — vocabulário fechado (categorias, status, gates, hardware)
  models.py              — ORM (7 tabelas novas, todas FK → avatars.id ON DELETE CASCADE)
  schemas.py              — contratos Pydantic (request/response da API)
  qa_checks.py            — QA determinístico (função pura, sem I/O)
  gate_requirements.py    — decide se um gate PODE ser aprovado (função pura, sem I/O)
  repository.py           — acesso a dados (mesmo padrão de dhf_avatars.repository:
                             cada função abre/fecha sua própria sessão)
  service.py               — orquestra repository + gate_requirements + Storage
  router.py                 — rotas FastAPI, montadas em /avatars/{avatar_id}/...
```

Mesma separação em camadas de `dhf_avatars` (router → service → repository → models),
mesmo padrão de erro (exceções de domínio traduzidas para `HTTPException` só no
router), mesmo padrão de lock otimista (`version` + `UPDATE ... WHERE version = X
RETURNING`).

## Entidades novas

| Tabela | Papel |
|---|---|
| `avatar_identity_locks` | Uma linha por versão de identidade (seção 5). Aprovado é imutável — re-travar cria uma NOVA linha (`identity_version + 1`) e marca a anterior `superseded`. Nunca sobrescreve. |
| `avatar_reference_assets` | Metadata de cada imagem de referência (nunca o binário — isso fica no Storage). `category`/`angle` identificam o slot; `qa_status`/`qa_detail` vêm do QA Engine; `upload_state`/`approved`/`rejection_reason` vêm da revisão humana. |
| `avatar_state_transitions` | Histórico **append-only** de avanço real de status — `from_status`, `to_status`, `actor`, `reason`, `evidence`, `quality_gate`, `avatar_version`. Nunca UPDATE/DELETE. |
| `avatar_quality_gates` | Estado ATUAL de cada gate (uma linha por `(avatar_id, gate_name)`). |
| `avatar_quality_gate_decisions` | Log **append-only** de toda aprovação/rejeição de gate (seção 33). |
| `avatar_derived_assets` | Placeholder por tipo de artefato futuro (mesh, textura, rig, ...) — `status` começa e permanece `not_generated` até a GPU real existir (seção 19). |
| `avatar_job_contracts` | Contrato de job futuro por tipo (seção 20) — `status='blocked'`, nunca executa nada (seção 21: "sem executar GPU"). |

## Identity Lock (seções 5-6)

Estrutura versionável de verdade (não texto livre): `IdentitySpec` agrega
`FaceIdentitySpec`, `EyeIdentitySpec`, `MouthIdentitySpec`, `HairIdentitySpec`,
`BodyIdentitySpec`, `HandIdentitySpec`, `ClothingIdentitySpec` — cada um validado pelo
Pydantic. Persistido como JSONB (mesmo padrão de `avatar_metadata` em `dhf_avatars`) —
a validação de forma acontece na camada Pydantic, não no banco.

Fluxo: `POST .../identity-lock` cria ou edita o draft atual; `POST
.../identity-lock/approve` trava (imutável a partir daí). Uma nova chamada de upsert
DEPOIS de aprovado cria uma nova versão em draft, sem tocar na aprovada — só quando essa
nova versão é aprovada é que a antiga vira `superseded` (na mesma operação atômica).

## Reference Asset Manifest (seções 7-12, 15-16)

`ReferenceAssetCategory` cobre as três famílias 360° (`head_360`, `half_body_360`,
`full_body_360`, cada uma com 36 ângulos de 10° via o campo `angle`), 32 categorias
especializadas e 19 expressões do master set — todas as strings exatas pedidas na
missão, sem adição nem omissão.

Upload real: `POST .../references` (multipart) roda o QA determinístico sobre os bytes
recebidos, escreve o arquivo em `03_AVATAR_IDENTITY_FOTOS/<slug>/v1/<categoria>/<slot>`
via `dhf_storage.factory.get_storage_provider().upload(...)` (a mesma pasta oficial já
usada pelo Storage do Google Drive) e só então persiste a linha de metadata. `GET
.../references/{asset_id}/content` faz o proxy do binário de volta — o frontend nunca
fala com o Drive diretamente.

`compute_multiview_completeness()` (`gate_requirements.py`) calcula o progresso
considerando sempre o asset **mais recente** por slot (uma recaptura supera a anterior
sem apagá-la — histórico preservado).

## QA Engine determinístico (seções 13-14)

`qa_checks.run_deterministic_checks()` — função pura, testável sem rede/DB/Storage:
checksum SHA-256 + duplicata exata, validade do arquivo (Pillow abre e decodifica),
dimensões mínimas, heurística de blur (variância de bordas via `ImageFilter.FIND_EDGES`
— calibrada empiricamente, ver `tests/avatar_factory/test_qa_checks.py`), heurística de
exposição (% de pixels saturados em preto/branco puro). `face_presence` fica
explicitamente `NOT_CHECKED` — a seção 13 permite pular quando não há biblioteca
CPU-friendly estável instalada, e este V1 não adiciona uma dependência pesada de
detecção facial só para isso.

Revisão humana: `POST .../references/{id}/approve` e `.../reject` (motivo obrigatório,
um dos 11 `RejectionReason` da missão).

## State machine e enforcement (seções 2-4, 25)

Os 13 status e a adjacência linear (`ALLOWED_STATUS_TRANSITIONS`) **já existiam** em
`dhf_avatars.schemas` e não foram alterados. O que esta missão adiciona é um
**segundo nível de exigência**: um `QualityGateName` por transição não-trivial —

```
identity → IDENTITY_LOCKED       rig         → RIGGED
multiview → MULTIVIEW_APPROVED   materials   → MATERIALS_APPROVED
mesh      → MESH_APPROVED        face        → FACE_APPROVED
                                  voice       → VOICE_APPROVED
                                  motion      → MOTION_APPROVED
                                  master      → MASTER_APPROVED
                                  production  → PRODUCTION_READY
```

As duas transições que só "iniciam trabalho" (`identity_locked→multiview_in_progress`,
`multiview_approved→mesh_in_progress`) não têm gate — nada para aprovar ainda; seguem
pelo `PATCH /avatars/{id}` genérico, exatamente como antes desta missão.

`POST .../quality-gates/{gate}/approve`:
1. Confere adjacência (`target_status` precisa ser o próximo permitido a partir do
   status atual) — reaproveita `ALLOWED_STATUS_TRANSITIONS` de `dhf_avatars`.
2. Busca os dados reais (`IdentityLock`, `ReferenceAsset`s ou `DerivedAsset`s conforme o
   gate) e chama `gate_requirements.check_*_gate()` — nunca aprova sem requisito
   satisfeito de verdade.
3. Se satisfeito: grava a decisão (append-only), avança `AvatarRecord.status`
   reutilizando `dhf_avatars.repository.update_avatar` (mesmo lock otimista) e grava a
   transição (append-only) com o `quality_gate` que autorizou.

Gates que dependem de GPU (`mesh`, `rig`, `materials`, `face`) checam a existência de um
`DerivedAssetRecord` `GENERATED` do tipo certo — **nunca existe nesta missão**, então
ficam honestamente bloqueados (`blocked_reason="PENDENTE_RTX_4090"`). `voice`/`motion`/
`master` dependem de subsistemas (voice bank, motion bank) totalmente fora do escopo.
`production` reconfirma que todos os outros 9 gates estão `pass`.

`POST .../quality-gates/{gate}/reject` grava a decisão sem mudar o status do avatar —
rejeição nunca regride nada, só documenta que a tentativa não foi aceita.

## API

Ver `core/avatar_factory/dhf_avatar_factory/router.py` para a lista completa — 17 rotas
sob `/avatars/{avatar_id}/...`: `identity-lock` (+ `/approve`), `references` (+
`/{id}/approve`, `/{id}/reject`, `/{id}/content`), `multiview`, `quality-gates` (+
`/{gate}/approve`, `/{gate}/reject`), `history`, `readiness`, `derived-assets`,
`job-contracts`, `factory` (view agregada — tudo que o dashboard precisa numa chamada).

## Frontend

`apps/web/src/pages/AvatarFactory.tsx` (rota `/avatars/:id/factory`, link a partir de
`Avatars.tsx`) — painel de Identity Lock, três `ImageViewer360` (um por família 360°,
com slider 0-350°, upload/aprovação/rejeição reais), grades de categorias
especializadas/expression (chips coloridos por estado, painel de upload sob demanda),
`SideBySideCompare` (Reference Master vs. ângulo atual — contrato pronto para "Reference
vs. Mesh render" quando existir mesh real), lista de quality gates com aprovação/
rejeição, checklist de production readiness e histórico de transições. Validado de
ponta a ponta num browser real (Playwright) contra a API e o Postgres reais.

## O que ainda depende da RTX 4090 real

Todo `DerivedAssetRecord` fica `not_generated`; todo `JobContractRecord` fica `blocked`
com `error` explicando o motivo; os gates `mesh`/`rig`/`materials`/`face` nunca
aprovam. Isso é o comportamento **correto e esperado** desta V1 — nada aqui finge um
resultado que a GPU ainda não produziu.
