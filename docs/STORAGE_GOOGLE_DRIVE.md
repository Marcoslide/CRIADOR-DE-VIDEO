# Google Drive Storage — Digital Human Video Factory

> V1 implementada e validada com OAuth User + `drive.file` em integração real.

## Decisão da V1

- autenticação: OAuth User;
- único escopo Drive: `https://www.googleapis.com/auth/drive.file`;
- root técnica: `CRIADOR DE VIDEO — STORAGE`, criada pelo aplicativo;
- a pasta histórica `CRIADOR DE VIDEO` não é consultada, alterada, movida nem apagada.

`drive.file` concede acesso por item. Como a root, as 18 pastas e todo ativo futuro são
criados pelo próprio aplicativo, o provider consegue operar todo o contrato sem acesso ao
restante do My Drive. Arquivos colocados manualmente na root não devem ser considerados
acessíveis; migrações devem ser feitas por upload do aplicativo ou seleção individual
explícita em uma futura integração com Google Picker.

## Bootstrap e persistência da root

O comando `bootstrap` executa OAuth Desktop se o token ainda não existe, depois:

1. tenta validar `GOOGLE_DRIVE_ROOT_FOLDER_ID`, quando configurado;
2. senão, carrega o ID do state file persistido;
3. se o state ficou obsoleto porque a pasta foi apagada, procura uma root criada pelo app;
4. faz discovery por nome **e** pela marca privada
   `appProperties.dhf_storage_root=v1`;
5. recusa ambiguidades se encontrar mais de uma root marcada;
6. cria a root somente quando nenhuma root marcada existe;
7. salva o ID atomicamente em arquivo `0600`;
8. cria apenas as pastas oficiais ausentes e recusa nomes oficiais duplicados.

Uma pasta manual com o mesmo nome não possui a marca privada e, portanto, nunca será
adotada por engano.

Os testes reais usam exclusivamente a área interna
`CRIADOR DE VIDEO — STORAGE/_integration_tests/<uuid>`. Ela é criada sob demanda pelo
provider, não conta entre as 18 pastas oficiais e sua limpeza envia artefatos para a
lixeira recuperável. O scratch operacional `02_SISTEMA_STORAGE/_tmp` continua disponível,
mas não é usado pela suíte de integração.

Quando `GOOGLE_DRIVE_ROOT_STATE_FILE` não é informado, o arquivo é derivado de
`GOOGLE_DRIVE_OAUTH_USER_FILE`. Por exemplo:

```text
google-drive-token.json
google-drive-token.storage-state.json
```

Em produção, onde o token costuma vir de `GOOGLE_DRIVE_OAUTH_USER_JSON`, configure o ID
emitido pelo bootstrap como `GOOGLE_DRIVE_ROOT_FOLDER_ID` no secret/config do ambiente.

## Configuração

```dotenv
GOOGLE_DRIVE_AUTH_MODE=oauth_user
GOOGLE_DRIVE_ROOT_FOLDER_NAME=CRIADOR DE VIDEO — STORAGE
GOOGLE_DRIVE_OAUTH_USER_FILE=/local/seguro/google-drive-token.json
```

O OAuth Client Desktop pode ser fornecido ao CLI pelo JSON baixado do Google Cloud. Como
alternativa, o par abaixo pode vir do secret manager:

```dotenv
GOOGLE_DRIVE_CLIENT_ID=...
GOOGLE_DRIVE_CLIENT_SECRET=...
```

Exatamente uma fonte de credencial de usuário deve existir: `_FILE` ou `_JSON`. O token,
refresh token e client secret nunca entram no Git, frontend, logs ou URLs.

### Comando inicial

```bash
uv run --project services/storage dhf-storage bootstrap \
  --client-secrets-file /local/seguro/client_secret.json \
  --token-file /local/seguro/google-drive-token.json
```

O consentimento usa browser do sistema e retorno loopback em `127.0.0.1`. Se o token já
existe, o comando o reutiliza e apenas valida/repara a árvore. Para obter um novo token:

```bash
uv run --project services/storage dhf-storage bootstrap \
  --client-secrets-file /local/seguro/client_secret.json \
  --token-file /local/seguro/google-drive-token.json \
  --reauthorize
```

## Testing, Production e AUTH_EXPIRED

Com OAuth Publishing Status `Testing`, tokens de usuários de teste para escopos Drive
expiram em sete dias. Isso é aceitável somente durante desenvolvimento.

Antes da operação contínua na RTX, o aplicativo precisa estar `In production` ou usar uma
alternativa Internal/Trusted permitida pelo Google. O refresh token ainda pode deixar de
funcionar por revogação, inatividade ou política administrativa.

Quando o endpoint de token devolve `invalid_grant`, o provider:

- não repete a renovação indefinidamente;
- levanta `StorageAuthExpiredError`;
- expõe `status=auth_expired` e `error_code=AUTH_EXPIRED`;
- mostra no frontend `Autorização expirada`;
- exige novo bootstrap OAuth com `--reauthorize`.

Outros erros permanecem sanitizados e nunca incluem token, URL de sessão ou corpo da
credencial.

O health check também consulta `about.get` (compatível com `drive.file`). Se o uso total
alcançar o limite da conta, o backend e o dashboard reportam `DEGRADED` com
`error_code=STORAGE_QUOTA_EXCEEDED`; a existência da root e das 18 pastas, sozinha, não é
suficiente para declarar o Storage `CONNECTED`.

## Validação real da V1

A Definition of Done foi executada contra My Drive real usando somente
`_integration_tests/<uuid>` e confirmou: bootstrap idempotente, 18/18 pastas, upload
resumable em múltiplos chunks, retomada após perda de resposta, download atômico,
checksum, exists, list, metadata, copy, move/rename, lixeira recuperável e sync
idempotente. O status só foi promovido a `CONNECTED` depois da aprovação integral dessa
suíte.

## Árvore oficial

O bootstrap cria idempotentemente estas 18 pastas:

```text
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

Todo `remote_path` deve começar por um desses nomes. Segmentos vazios, `.`, `..` e byte
nulo são rejeitados. Leituras nunca criam pastas; upload e sync podem criar somente
subpastas abaixo da árvore oficial.

`delete()` sem `allow_permanent=True` só funciona em `02_SISTEMA_STORAGE/_tmp/` e move o
arquivo para a lixeira recuperável. Fora do scratch, a chamada é bloqueada antes da rede.

## Garantias técnicas

- upload resumable em blocos múltiplos de 256 KiB, com `Content-Range`, consulta do offset
  confirmado e retomada apenas dos bytes faltantes;
- download em streaming para temporário, retry desde zero e troca atômica;
- checksum MD5 do conteúdo comparado com `md5Checksum` do Drive em upload e download;
- list, metadata, exists, copy e move com bloqueio de colisão no destino;
- sync por checksum;
- retry/backoff apenas para transporte, `429` e `5xx`;
- health real valida token, marca/nome/ID da root e as 18 pastas.

## Verificação

```bash
uv run --project services/storage dhf-storage check
uv run --all-packages pytest tests/storage -m "not integration"
uv run --all-packages pytest tests/storage/test_google_drive_integration.py -m integration -vv
```

Os testes reais criam nomes únicos somente no scratch, exercitam o contrato completo e
movem os temporários para a lixeira. Um teste entrega o primeiro bloco ao Google, perde a
resposta localmente e comprova a retomada na sessão real. Sem token, esses testes ficam
`SKIPPED`, nunca geram sucesso falso.
