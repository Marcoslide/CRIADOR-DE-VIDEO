# GPU ENGINE SETUP PLAN — Hostinger RTX 5090

> Status: plano operacional documental; nenhum provisionamento foi executado por este documento.
> Escopo: nó GPU da Digital Human Video Factory, Realismo P0.
> Data-base da revisão: 2026-09-12.

## 1. Decisões confirmadas

O plano parte da configuração já auditada no hPanel da Hostinger:

| Item | Configuração planejada |
|---|---|
| GPU | NVIDIA GeForce RTX 5090 |
| VRAM | 32 GB |
| CPU | 32 vCPU |
| RAM | 64 GB |
| Disco | SSD de 500 GB |
| Região | Miami |
| Sistema | Ubuntu 24.04 LTS |

A RTX 5090 **existe no catálogo/painel auditado**. O risco de aquisição remanescente não é
“o plano talvez não existir”; é somente a disponibilidade imediata de estoque na região de
Miami no instante do provisionamento. Reconfirmar esse único ponto antes de contratar.

O SSD do nó é hot storage, cache e scratch. Ele não substitui o Storage Master. A ativação
do Google Drive permanece em missão separada, descrita em `GOOGLE_DRIVE_ACTIVATION.md` quando
esse documento estiver presente no workspace. Este plano não muda credenciais, OAuth,
service accounts nem código de storage.

## 2. Arquitetura V1 aprovada

```text
Aplicação/API
   └── fila de jobs
       └── GPU Worker — Hostinger RTX 5090 / Ubuntu 24.04
           ├── NVIDIA Driver + CUDA 12.9
           ├── TensorRT 10.13.x
           ├── Docker + NVIDIA Container Toolkit
           ├── Audio2Face-3D SDK + modelo oficial
           ├── Unreal Engine 5.8 + MetaHuman 5.8
           ├── FFmpeg + NVENC
           └── telemetria e benchmark
```

### 2.1 Audio2Face: separação correta de componentes e licenças

Para a V1, adotar execução própria no nó: **RTX 5090 + Audio2Face-3D SDK + modelo oficial
Audio2Face-3D + TensorRT + Unreal**.

- O código do Audio2Face-3D SDK é publicado pela NVIDIA sob licença MIT.
- Os pesos oficiais Audio2Face-3D têm licença NVIDIA Open Model própria; aceitar e arquivar
  a versão vigente antes de baixar.
- Audio2Emotion tem licença própria e somente deve entrar se for necessário e aprovado.
- Audio2Face-3D NIM é um produto de implantação separado, sujeito ao NVIDIA Software License
  Agreement e aos termos de produtos de IA. NIM não é requisito técnico nem comercial para
  usar o SDK na V1.
- Não assumir licença NVIDIA AI Enterprise para o SDK e não assumir preço por minuto. Se NIM
  for avaliado no futuro, fazer análise comercial e jurídica separada.

O SDK oficial atualmente declara Linux Ubuntu 20.04+, CUDA `>=12.8,<13.0` (12.9 recomendada),
Python `>=3.8,<=3.10.x` e TensorRT `>=10.13,<11.0`. Esses limites formam uma **ilha de versões**:
não instalar automaticamente o CUDA/TensorRT mais novo sem confirmar compatibilidade.

### 2.2 MetaHuman: Linux é caminho principal

MetaHuman 5.8 disponibiliza no Linux o MetaHuman Creator e animação facial offline e em tempo
real. Portanto, nenhuma máquina Windows é recomendada agora. Limitações documentadas:

- animação corporal do MetaHuman Animator permanece disponível apenas no Windows;
- animação facial em tempo real no Linux requer Live Link Face;
- a solução de Animator é de editor, não um runtime para o player.

Windows é apenas fallback futuro, acionado se um teste real de corpo, markerless ou outro
workflow específico provar essa necessidade.

### 2.3 Gate de compatibilidade Unreal ↔ Audio2Face

O plugin Audio2Face-3D para Unreal publicado pela NVIDIA lista suporte oficial até versões
anteriores do Unreal, enquanto o alvo deste projeto é Unreal/MetaHuman 5.8. Antes de integrar:

1. testar o plugin em uma cópia descartável do projeto 5.8;
2. se não compilar ou não funcionar, manter inferência no SDK Linux e construir/importar o
   resultado por uma interface estável (curvas/blendshapes/arquivo de animação);
3. não rebaixar Unreal nem trocar a arquitetura sem benchmark e aprovação;
4. não declarar integração pronta até produzir animação real em um MetaHuman do projeto.

## 3. Princípios operacionais

- **Realismo P0:** qualidade visual e estabilidade vencem velocidade e custo.
- **Zero fake:** cada etapa termina com evidência real; instalação não é inferida pela
  existência de uma pasta ou variável.
- **Versões pinadas:** registrar driver, CUDA, TensorRT, Docker, SDK, modelo, Unreal e plugins
  em um manifesto do ambiente antes do primeiro benchmark.
- **Segredos fora do Git:** chaves ficam em secret manager/variáveis protegidas, nunca em
  comandos, logs, imagens ou commits.
- **Menor exposição:** SSH por chave e allowlist de IP; API/Redis/PostgreSQL não ficam
  publicamente acessíveis.
- **Rollback antes da mudança:** snapshot do volume e registro dos pacotes antes de upgrades.
- **Um benchmark por mudança:** não atualizar simultaneamente driver, CUDA, TensorRT e engine.

## 4. Layout previsto no nó

```text
/opt/dhvf/
├── app/                 clone do repositório
├── engines/
│   ├── unreal-5.8/
│   └── audio2face-3d-sdk/
├── models/              modelos locais licenciados e versionados
├── venvs/
├── benchmarks/
└── manifests/           inventário de versões e evidências sem segredos

/var/lib/dhvf/
├── cache/
├── scratch/
└── renders/

/var/log/dhvf/
```

Não armazenar o único exemplar de qualquer asset nesses diretórios. Conteúdo de
`cache/`, `scratch/` e `renders/` deve ser reconstruível ou sincronizado com o Storage Master.

## 5. Gates de aprovação

| Gate | Resultado necessário |
|---|---|
| G0 — compra | RTX 5090/32 GB disponível em Miami com 32 vCPU, 64 GB RAM e 500 GB SSD |
| G1 — host | SSH por chave, Ubuntu 24.04, firewall e disco corretos |
| G2 — GPU | driver, `nvidia-smi`, CUDA e TensorRT coerentes |
| G3 — containers | container enxerga a RTX 5090 e executa carga CUDA |
| G4 — mídia | FFmpeg lista NVENC e produz arquivo decodificável |
| G5 — engines | Unreal 5.8 abre projeto; SDK A2F executa modelo oficial |
| G6 — integração | áudio real gera animação aplicável a MetaHuman real |
| G7 — P0 | benchmark visual, técnico e operacional aprovado e reproduzível |

## 6. Checklist operacional obrigatório

Executar estritamente na sequência abaixo. Substituir valores entre `<...>` somente depois
de registrá-los no manifesto do ambiente.

### 6.1 PROVISIONAMENTO

**COMANDO:** no hPanel, selecionar GPU Hosting → RTX 5090 → 32 GB VRAM → 32 vCPU →
64 GB RAM → 500 GB SSD → Miami → Ubuntu 24.04; antes de confirmar, salvar a tela de resumo
e o preço total. Não inserir credenciais do projeto na imagem inicial.

**RESULTADO ESPERADO:** instância ativa com IP público, console de recuperação e acesso à
gestão de rede/snapshot.

**TESTE:** comparar fatura e inventário do hPanel, campo a campo, com a tabela da seção 1.

**CRITÉRIO DE APROVAÇÃO:** todos os sete itens coincidem; estoque em Miami confirmado no
momento da compra; nenhuma troca automática por outra GPU/região.

**ROLLBACK/DIAGNÓSTICO:** não confirmar a compra se houver divergência. Se a instância nascer
com perfil errado, registrar evidência, desligar e usar cancelamento/reprovisionamento do
hPanel antes de instalar qualquer componente.

### 6.2 SSH

**COMANDO:**

```bash
ssh-keygen -t ed25519 -a 64 -f <caminho-seguro>/dhvf_hostinger -C dhvf-gpu
ssh -i <caminho-seguro>/dhvf_hostinger <usuario>@<ip-do-no>
```

Depois de validar a chave, restringir SSH por IP no firewall do provedor e desabilitar login
por senha/root conforme a política operacional.

**RESULTADO ESPERADO:** sessão por chave, usuário administrativo não-root e host key conhecida.

**TESTE:** abrir uma segunda sessão por chave antes de fechar a primeira; executar
`id && hostnamectl && last -n 5`.

**CRITÉRIO DE APROVAÇÃO:** duas conexões por chave funcionam; senha não é necessária; porta
SSH não está aberta para origens fora da allowlist.

**ROLLBACK/DIAGNÓSTICO:** manter a primeira sessão e o console web abertos enquanto muda SSH.
Em falha, reverter `sshd_config` pelo console e consultar `journalctl -u ssh --since -15m`.

### 6.3 UBUNTU

**COMANDO:**

```bash
cat /etc/os-release
uname -a
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
df -hT
sudo apt-get update
sudo apt-get dist-upgrade -y
sudo reboot
```

**RESULTADO ESPERADO:** Ubuntu 24.04 LTS atualizado, arquitetura x86_64, disco de 500 GB
visível e filesystem íntegro.

**TESTE:** após reboot, `cat /etc/os-release && uname -r && systemctl --failed`.

**CRITÉRIO DE APROVAÇÃO:** `VERSION_ID="24.04"`, nenhum serviço essencial em falha, horário/NTP
corretos e espaço útil compatível com o plano.

**ROLLBACK/DIAGNÓSTICO:** criar snapshot antes do upgrade. Se o novo kernel impedir boot,
selecionar kernel anterior no console/GRUB e revisar `/var/log/apt/history.log`.

### 6.4 NVIDIA DRIVER

**COMANDO:** identificar primeiro o driver recomendado e instalar pelo gerenciador de pacotes,
sem usar instalador `.run` sobre pacotes APT:

```bash
sudo apt-get install -y ubuntu-drivers-common
ubuntu-drivers devices
sudo ubuntu-drivers install
sudo reboot
```

**RESULTADO ESPERADO:** módulo NVIDIA assinado/carregado e RTX 5090 reconhecida.

**TESTE:** `lsmod | grep '^nvidia' && lspci -nnk | grep -A3 -i nvidia`.

**CRITÉRIO DE APROVAÇÃO:** a GPU usa o driver `nvidia`; não há erro Xid, conflito `nouveau`
nem módulo ausente em `journalctl -k`.

**ROLLBACK/DIAGNÓSTICO:** usar snapshot; inspecionar `journalctl -k -b`, Secure Boot e DKMS.
Reinstalar somente o pacote de driver previamente registrado e reiniciar.

### 6.5 NVIDIA-SMI

**COMANDO:**

```bash
nvidia-smi
nvidia-smi --query-gpu=name,uuid,driver_version,memory.total,pstate,temperature.gpu,power.limit --format=csv
nvidia-smi -q
```

**RESULTADO ESPERADO:** uma RTX 5090, aproximadamente 32 GB de VRAM, sem processos estranhos e
sem erros de driver.

**TESTE:** executar cinco leituras em intervalos curtos e revisar `dmesg -T | grep -iE 'NVRM|Xid'`.

**CRITÉRIO DE APROVAÇÃO:** nome, UUID e VRAM permanecem estáveis; `nvidia-smi` retorna zero;
nenhum Xid; temperatura de idle aceitável para o provedor.

**ROLLBACK/DIAGNÓSTICO:** não instalar CUDA se este gate falhar. Revalidar perfil da VM,
driver, kernel e pass-through com suporte Hostinger.

### 6.6 CUDA

**COMANDO:** pinagem inicial compatível com o Audio2Face-3D SDK:

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update
sudo apt-get install -y cuda-toolkit-12-9
/usr/local/cuda-12.9/bin/nvcc --version
```

**RESULTADO ESPERADO:** CUDA Toolkit 12.9 disponível sem substituir silenciosamente o driver
aprovado.

**TESTE:** compilar e executar `deviceQuery` dos samples CUDA ou um programa mínimo que aloque
memória, execute kernel e sincronize sem erro.

**CRITÉRIO DE APROVAÇÃO:** `nvcc` informa 12.9; o sample detecta uma RTX 5090 e termina `PASS`;
driver continua saudável.

**ROLLBACK/DIAGNÓSTICO:** revisar `apt-cache policy 'cuda*'` e compatibilidade do driver. Remover
somente os pacotes CUDA instalados nesta etapa; não purgar o driver aprovado sem diagnóstico.

### 6.7 TENSORRT

**COMANDO:** selecionar no repositório NVIDIA uma versão `>=10.13,<11.0` compilada para CUDA
12.9, registrar a versão exata e então instalar os pacotes Debian correspondentes:

```bash
apt-cache madison tensorrt
sudo apt-get install -y tensorrt=<versao-10.13.x-aprovada> tensorrt-dev=<mesma-versao>
trtexec --version
dpkg-query -W 'libnvinfer*' 'tensorrt*'
```

**RESULTADO ESPERADO:** runtime, headers e `trtexec` da mesma família 10.13.x.

**TESTE:** construir e executar um engine ONNX pequeno com `trtexec`, incluindo uma rodada FP16,
e salvar latência, throughput e uso de VRAM.

**CRITÉRIO DE APROVAÇÃO:** engine é criado e executado sem fallback/erro; CUDA e TensorRT estão
na matriz exigida pelo SDK; todos os pacotes têm versão registrada.

**ROLLBACK/DIAGNÓSTICO:** não aceitar resolução automática para TensorRT 11. Remover somente
pacotes `tensorrt/libnvinfer` desta tentativa, restaurar pinagem e consultar logs do `trtexec`.

### 6.8 DOCKER

**COMANDO:**

```bash
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker <usuario-operacional>
docker version
docker compose version
```

Abrir nova sessão depois de alterar o grupo.

**RESULTADO ESPERADO:** daemon ativo no boot, Compose v2 e usuário operacional autorizado sem
expor o socket Docker pela rede.

**TESTE:** `docker run --rm hello-world && systemctl is-enabled docker && systemctl is-active docker`.

**CRITÉRIO DE APROVAÇÃO:** cliente/daemon respondem; container termina com sucesso; socket só
local; nenhum registry privado foi configurado com segredo em texto claro.

**ROLLBACK/DIAGNÓSTICO:** `journalctl -u docker --since -15m`, `docker info` e validação de espaço
em `/var/lib/docker`; restaurar `/etc/docker/daemon.json` anterior se houve mudança.

### 6.9 NVIDIA CONTAINER TOOLKIT

**COMANDO:** seguir o repositório oficial NVIDIA e configurar o runtime Docker:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -sL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker run --rm --gpus all ubuntu:24.04 nvidia-smi
```

**RESULTADO ESPERADO:** container recebe somente a GPU solicitada e executa `nvidia-smi`.

**TESTE:** comparar UUID, driver e VRAM dentro/fora do container; executar também um container
sem `--gpus` e confirmar que não recebeu GPU.

**CRITÉRIO DE APROVAÇÃO:** teste com `--gpus all` passa; teste sem flag não expõe dispositivos;
Docker reinicia sem quebrar containers existentes.

**ROLLBACK/DIAGNÓSTICO:** restaurar backup de `/etc/docker/daemon.json`; rodar
`nvidia-ctk runtime configure --runtime=docker` novamente e revisar logs do runtime.

### 6.10 NVENC

**COMANDO:**

```bash
sudo apt-get install -y ffmpeg
ffmpeg -hide_banner -encoders | grep nvenc
ffmpeg -f lavfi -i testsrc2=size=1920x1080:rate=30 -t 10 -c:v h264_nvenc -preset p5 /var/lib/dhvf/scratch/nvenc-smoke.mp4
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate -of default=nw=1 /var/lib/dhvf/scratch/nvenc-smoke.mp4
```

**RESULTADO ESPERADO:** `h264_nvenc`/`hevc_nvenc` listados e vídeo de teste válido.

**TESTE:** reproduzir/decodificar o arquivo inteiro com `ffmpeg -v error -i <arquivo> -f null -`
e observar uso do encoder no `nvidia-smi dmon`.

**CRITÉRIO DE APROVAÇÃO:** exit code zero, 300 frames aproximados, dimensões/fps corretos,
arquivo sem erro de decodificação e atividade NVENC comprovada.

**ROLLBACK/DIAGNÓSTICO:** se o encoder não existir, instalar build FFmpeg com suporte NVENC ou
compilar conforme o NVIDIA Video Codec SDK; não mascarar com encode por CPU.

### 6.11 PYTORCH GPU TEST

**COMANDO:** criar ambiente de smoke test isolado; escolher no seletor oficial do PyTorch o
wheel CUDA compatível com o driver e registrar a versão:

```bash
python3 -m venv /opt/dhvf/venvs/pytorch-smoke
/opt/dhvf/venvs/pytorch-smoke/bin/pip install --upgrade pip
/opt/dhvf/venvs/pytorch-smoke/bin/pip install torch --index-url https://download.pytorch.org/whl/cu128
/opt/dhvf/venvs/pytorch-smoke/bin/python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0)); x=torch.randn((8192,8192),device='cuda'); y=x@x; torch.cuda.synchronize(); print(float(y[0,0]), torch.cuda.memory_allocated())"
```

**RESULTADO ESPERADO:** PyTorch reconhece a RTX 5090 e executa multiplicação na GPU.

**TESTE:** repetir três vezes, acompanhar VRAM/temperatura e confirmar que a memória é liberada
quando o processo termina.

**CRITÉRIO DE APROVAÇÃO:** `torch.cuda.is_available()` implícito no teste, zero exceções, valor
finito, VRAM volta ao baseline e nenhum Xid/OOM.

**ROLLBACK/DIAGNÓSTICO:** apagar somente o venv descartável; revisar wheel/driver/arquitetura.
Este smoke test não define a versão Python do Audio2Face, que terá ambiente Python 3.10 próprio.

### 6.12 MONITORING

**COMANDO:** iniciar coleta diagnóstica e criar baseline antes de instalar engines:

```bash
mkdir -p /opt/dhvf/benchmarks /opt/dhvf/manifests
nvidia-smi --query-gpu=timestamp,name,uuid,driver_version,temperature.gpu,power.draw,power.limit,memory.used,memory.total,utilization.gpu --format=csv -l 5
```

Em produção, substituir a sessão por exporter/serviço supervisionado aprovado, com métricas de
GPU, CPU, RAM, disco, processos, fila, tempo de job, falhas e OOM; alertas não podem conter áudio,
frames, tokens ou segredos.

**RESULTADO ESPERADO:** série temporal consultável e baseline de idle/carga.

**TESTE:** gerar carga PyTorch/NVENC, confirmar mudança das métricas e disparar alerta de teste.

**CRITÉRIO DE APROVAÇÃO:** métricas têm timestamp, UUID da GPU e retenção; alerta chega ao canal
aprovado; lacuna de coleta e disco cheio são detectáveis.

**ROLLBACK/DIAGNÓSTICO:** parar apenas o coletor novo; revisar service/container logs, porta local,
permissões e cardinalidade. Nunca desativar `nvidia-smi` de diagnóstico.

### 6.13 DEPLOY REPO

**COMANDO:**

```bash
sudo install -d -o <usuario-operacional> -g <grupo-operacional> /opt/dhvf/app
git clone https://github.com/Marcoslide/CRIADOR-DE-VIDEO.git /opt/dhvf/app
cd /opt/dhvf/app
git checkout main
git rev-parse HEAD
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
```

Injetar segredos somente pelo mecanismo protegido aprovado; nunca copiar `.env.example` como
produção.

**RESULTADO ESPERADO:** clone íntegro, commit registrado e configuração Compose válida.

**TESTE:** rodar lint/testes do README, varredura de segredos e `docker compose config` com
variáveis de teste não sensíveis antes de subir serviços.

**CRITÉRIO DE APROVAÇÃO:** working tree limpa, commit conhecido, testes verdes, nenhum segredo
versionado e portas internas não expostas publicamente.

**ROLLBACK/DIAGNÓSTICO:** manter releases por commit/diretório e voltar o symlink/deploy ao commit
anterior; não usar `git reset --hard` sobre diretório com dados ou mudanças não preservadas.

### 6.14 UNREAL

**COMANDO:** com conta GitHub vinculada à Epic e acesso oficial ao repositório, compilar a tag/
branch 5.8 pinada em diretório próprio:

```bash
git clone --depth 1 --branch 5.8 https://github.com/EpicGames/UnrealEngine.git /opt/dhvf/engines/unreal-5.8
cd /opt/dhvf/engines/unreal-5.8
./Setup.sh
./GenerateProjectFiles.sh
make -j16
Engine/Binaries/Linux/UnrealEditor -Version
```

**RESULTADO ESPERADO:** Unreal Editor 5.8 inicia no Linux e detecta Vulkan/RTX 5090.

**TESTE:** abrir projeto mínimo e projeto MetaHuman em modo editor; renderizar quadro de teste;
reabrir após reboot; registrar tempo, VRAM e logs.

**CRITÉRIO DE APROVAÇÃO:** versão 5.8 confirmada, editor estável, shader compilation termina,
quadro existe e não contém erro de RHI/GPU. MetaHuman Creator abre no Linux.

**ROLLBACK/DIAGNÓSTICO:** preservar logs em `Saved/Logs`; testar `-NullRHI` para separar falha de
projeto de falha gráfica; remover apenas o build descartável e restaurar versão pinada anterior.

### 6.15 AUDIO2FACE

**COMANDO:** construir o SDK oficial em ambiente pinado, usando TensorRT 10.13.x e CUDA 12.9:

```bash
git clone https://github.com/NVIDIA/Audio2Face-3D-SDK.git /opt/dhvf/engines/audio2face-3d-sdk
cd /opt/dhvf/engines/audio2face-3d-sdk
git checkout <commit-ou-tag-aprovada>
git lfs pull
./fetch_deps.sh release
export DHVF_TENSORRT_ROOT_DIR=<diretorio-tensorrt-10.13.x>
TENSORRT_ROOT_DIR="$DHVF_TENSORRT_ROOT_DIR" ./build.sh all release
```

Baixar um modelo oficial Audio2Face-3D aprovado, aceitar sua licença própria e guardar hash,
model card e versão. NIM não participa deste gate.

**RESULTADO ESPERADO:** bibliotecas `audio2face-sdk`/`audio2x-sdk` geradas e modelo carregável.

**TESTE:** executar sample oficial com áudio PT-BR conhecido; salvar saída de blendshapes/curvas,
tempo, FPS, VRAM, logs e hash do modelo; aplicar a saída em personagem de teste.

**CRITÉRIO DE APROVAÇÃO:** inferência GPU real, saída não vazia, duração sincronizada ao áudio,
sem OOM/NaN e resultado visual revisável. Licenças do SDK/modelo arquivadas.

**ROLLBACK/DIAGNÓSTICO:** manter build por commit; comparar CUDA/TensorRT/Python/model card;
executar sample oficial sem Unreal para isolar integração. Se o plugin não suportar UE 5.8,
usar a saída do SDK — não introduzir NIM nem Windows como atalho silencioso.

### 6.16 METAHUMAN

**COMANDO:** no Unreal 5.8, habilitar MetaHuman Creator e MetaHuman Animator, importar o Mesh
Master aprovado e executar **MetaHuman Creator → From Custom Mesh → Rig**. Para smoke de editor:

```bash
/opt/dhvf/engines/unreal-5.8/Engine/Binaries/Linux/UnrealEditor <projeto-uproject> -log
```

**RESULTADO ESPERADO:** personagem MetaHuman baseado no mesh aprovado, com DNA/rig, materiais,
olhos, boca e groom vinculados, pronto para receber animação facial.

**TESTE:** no Linux, executar solve facial offline e aplicar o resultado A2F; revisar neutral,
fonemas, piscadas, olhar, dentes/língua, microexpressões e close contínuo de pelo menos 8 s.

**CRITÉRIO DE APROVAÇÃO:** identidade preservada contra Master Reference; nenhum defeito P0;
rig não quebra em poses extremas; animação é reproduzível após reabrir o projeto. Teste de corpo
não bloqueia este gate Linux e não autoriza automaticamente uma máquina Windows.

**ROLLBACK/DIAGNÓSTICO:** duplicar o asset antes de conform/rig; voltar à versão anterior do
MetaHuman, Mesh Master ou materiais; isolar falhas em mesh, rig, solve facial e A2F. Windows só
entra como fallback se um teste documentado provar requisito exclusivo.

### 6.17 BENCHMARK

**COMANDO:** executar um pacote fixo e versionado contendo: áudio PT-BR, animação facial,
close de 8 s, meio-corpo, cabelo, roupa, olhos/boca/mãos e render 4K; coletar simultaneamente
tempo por estágio, FPS, VRAM pico, RAM, temperatura, potência, falhas, retries e hashes.

**RESULTADO ESPERADO:** pacote de evidências reproduzível com mídia final, manifest, logs
sanitizados e métricas técnicas.

**TESTE:** repetir três vezes com host em estado conhecido; comparar A2F SDK e MetaHuman
Animator facial quando aplicável; revisão lado a lado Reference × Render por duas pessoas.

**CRITÉRIO DE APROVAÇÃO:** zero falha P0; sem OOM/Xid; close de 8 s aprovado; sincronismo labial,
identidade, olhos, boca, pele, cabelo, mãos e roupa aprovados; variação entre execuções explicada;
todo artefato possui versão/hash e pode ser reproduzido.

**ROLLBACK/DIAGNÓSTICO:** se qualquer P0 falhar, reprovar o pacote inteiro, preservar evidência,
identificar o primeiro estágio divergente e repetir somente a partir dele. Não compensar defeito
de identidade/rig com pós-produção.

## 7. Registro mínimo por execução

```yaml
run_id: <uuid>
host:
  provider: hostinger
  region: miami
  gpu_name: <nvidia-smi>
  gpu_uuid: <nvidia-smi>
versions:
  driver: <versao>
  cuda: 12.9
  tensorrt: <10.13.x>
  docker: <versao>
  audio2face_sdk_commit: <sha>
  audio2face_model: <nome-versao-hash>
  unreal: 5.8
  metahuman: 5.8
inputs:
  audio_sha256: <hash>
  avatar_version: <versao>
outputs:
  animation_sha256: <hash>
  render_sha256: <hash>
metrics:
  wall_time_s: <valor>
  peak_vram_mib: <valor>
  peak_ram_mib: <valor>
  max_temperature_c: <valor>
result: approved|rejected
rejection_reasons: []
```

## 8. Fontes oficiais

- [MetaHuman 5.8 Release Notes — Epic Games](https://dev.epicgames.com/documentation/metahuman/metahuman-5-8-release-notes-in-unreal-engine)
- [MetaHuman Creator Import Tools / From Custom Mesh — Epic Games](https://dev.epicgames.com/documentation/metahuman/metahuman-creator-import-tools-in-unreal-engine)
- [Audio2Face-3D collection, componentes e licenças — NVIDIA](https://github.com/NVIDIA/Audio2Face-3D/blob/release/README.md)
- [Audio2Face-3D SDK, requisitos e build Linux — NVIDIA](https://github.com/NVIDIA/Audio2Face-3D-SDK)
- [CUDA Installation Guide for Linux — NVIDIA](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/)
- [TensorRT Installation — NVIDIA](https://docs.nvidia.com/deeplearning/tensorrt/latest/installing-tensorrt/)
- [NVIDIA Container Toolkit — NVIDIA](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- [FFmpeg com NVENC/NVDEC — NVIDIA](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.1/ffmpeg-with-nvidia-gpu/index.html)

## 9. Ordem executiva final

**PROVISIONAMENTO → SSH → UBUNTU → NVIDIA DRIVER → NVIDIA-SMI → CUDA → TENSORRT →
DOCKER → NVIDIA CONTAINER TOOLKIT → NVENC → PYTORCH GPU TEST → MONITORING → DEPLOY REPO →
UNREAL → AUDIO2FACE → METAHUMAN → BENCHMARK**
