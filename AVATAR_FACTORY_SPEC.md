# AVATAR FACTORY SPEC — Realism P0

> Status: especificação operacional da fábrica de avatares; não declara avatar produzido.
> Prioridade absoluta: identidade e realismo acima de velocidade, custo e volume.
> Data-base da revisão: 2026-09-12.

## 1. Objetivo e fluxo aprovado

Produzir um Digital Human que preserve a identidade do performer e suporte vídeo 4K com
close facial contínuo de pelo menos 8 segundos sem aparência de “avatar”, face swap ou
talking head genérico.

Fluxo preferencial:

```text
MULTIVIEW
  → MESH MASTER
  → REFINEMENT
  → METAHUMAN CREATOR
  → FROM CUSTOM MESH
  → RIG
  → LOOKDEV
  → PERFORMANCE TEST
  → FINAL AVATAR QUALITY GATE
```

MetaHuman 5.8 permite MetaHuman Creator e animação facial offline no Linux. O nó RTX 5090
com Ubuntu 24.04 é o caminho principal. Windows não é dependência desta especificação; fica
apenas como fallback se um teste real de body capture, markerless ou workflow específico
documentar uma função exclusiva.

## 2. Regras invariáveis

1. **Consentimento e direitos:** captura, reconstrução, voz e uso comercial exigem autorização
   documentada do performer e escopo de uso conhecido.
2. **Sem filtro de beleza:** não usar retoque que mude geometria, poros, assimetrias, idade,
   cor real da pele, linha capilar, dentes ou proporções.
3. **Cor e lente controladas:** cada sessão registra câmera, lente, distância, exposição,
   white balance, iluminação, chart de cor e escala física.
4. **Neutral consistente:** postura, expressão, cabelo e roupa não podem variar silenciosamente
   entre ângulos usados na reconstrução.
5. **Identity Lock imutável:** após aprovação, toda versão é comparada ao pacote bloqueado.
   Mudança intencional gera nova versão e nova aprovação; nunca sobrescreve a anterior.
6. **Separar fonte e derivado:** RAW/original, proxy, máscara, mesh, textura, rig e render têm
   hashes e proveniência próprios.
7. **Zero fake:** um estágio somente fica aprovado se o arquivo existe, abre e passou pelo teste
   descrito. Uma renderização bonita não prova topologia, rig ou identidade corretos.
8. **Gate bloqueante:** rejeição numa dependência impede promover os estágios seguintes.
9. **Sem score mágico:** medidas auxiliam; identidade e Realismo P0 exigem comparação visual
   Reference × Render e aprovação humana registrada.
10. **Dados sensíveis:** fotos biométricas e scans têm acesso mínimo, trilha de auditoria e
    política de retenção. Nenhum ativo pessoal entra em log, issue ou commit.

## 3. Manifesto mínimo de cada asset

```yaml
asset_id: <uuid>
avatar_id: <uuid>
avatar_version: <vN>
stage: <stage_code>
source_asset_ids: []
capture_session_id: <id-ou-null>
filename: <nome>
sha256: <hash>
mime_type: <tipo>
size_bytes: <valor>
dimensions_or_geometry: <resolucao-ou-vertices-faces>
color_space: <valor-ou-null>
units: <mm-cm-m-ou-null>
tool_and_version: <valor>
operator: <id>
created_at_utc: <timestamp>
status: draft|in_review|approved|rejected|superseded
reviewer: <id-ou-null>
rejection_reasons: []
```

O local definitivo de armazenamento e sua ativação são tratados separadamente em
`GOOGLE_DRIVE_ACTIVATION.md` quando disponível. Esta especificação define conteúdo e gates;
não altera Drive, credenciais ou código de storage.

## 4. Convenção de captura

- Usar nomes determinísticos: `<avatar>_<versao>_<stage>_<camera>_<angulo>_<take>.<ext>`.
- Ângulos 360: 36 posições a cada 10°, numeradas `000` a `350`, salvo rig de captura com
  sincronização superior documentada.
- Incluir em cada sessão: chart de cor, escala métrica, slate com ID/take e um frame neutro.
- Capturar RAW quando suportado; preservar originais e gerar proxies separados.
- Bloquear exposição, foco, white balance e distância; sem modo retrato, HDR variável,
  estabilização que remapeie o rosto ou correção geométrica não registrada.
- Preferir luz difusa, uniforme e polarização cruzada para textura; capturar conjunto adicional
  de lookdev com luz dirigida sem misturá-lo à reconstrução.
- Fundo matte sem reflexos e contraste suficiente para máscara; não usar chroma que contamine
  pele, olhos, cabelo ou roupa.

## 5. Pipeline operacional por estágio

### 5.1 MASTER REFERENCE

**ENTRADA:** performer autorizado; briefing de identidade; sessão de referência calibrada;
frontal neutra, perfis esquerdo/direito, três-quartos, corpo inteiro, chart de cor, escala e
medidas físicas essenciais.

**PROCESSO:** selecionar imagens canônicas sem filtro; revelar RAW de modo neutro; corrigir apenas
lente/cor com perfil registrado; montar prancha Reference A com rosto, corpo, detalhes e medidas;
gerar hashes; registrar câmera, lente, distância, luz e data.

**SAÍDA:** pacote `MASTER_REFERENCE_vN` imutável, contato 2D, originais, proxies color-managed,
medidas, metadata, autorização e manifest.

**CRITÉRIO DE REPROVAÇÃO:** autorização ausente; imagem desfocada/comprimida/retocada; white balance
inconsistente; perfil ou corpo oculto; proporção sem escala; referências de sessões com mudanças
de aparência não declaradas.

**DEPENDÊNCIAS:** consentimento aprovado, protocolo de captura, câmera/lente calibradas, chart de
cor e armazenamento protegido disponíveis.

### 5.2 IDENTITY LOCK

**ENTRADA:** `MASTER_REFERENCE_vN`, medidas e conjunto de landmarks/silhuetas das vistas canônicas.

**PROCESSO:** marcar traços não negociáveis: formato craniano, linha capilar, sobrancelhas, olhos,
pálpebras, nariz, lábios, mandíbula, orelhas, assimetrias, marcas, proporções corporais e mãos;
definir overlays frontal/perfil/três-quartos; aprovar com performer/responsável; assinar manifest.

**SAÍDA:** `IDENTITY_LOCK_vN` com referências bloqueadas, overlays, landmarks, tolerâncias de
comparação, aprovadores, timestamp e hashes.

**CRITÉRIO DE REPROVAÇÃO:** aprovação verbal sem registro; média/simetrização que apague traços;
landmarks inconsistentes; arquivo editável sem versão; divergência entre medidas e fotos.

**DEPENDÊNCIAS:** Master Reference aprovado e revisor de identidade designado.

### 5.3 HEAD 360

**ENTRADA:** performer em expressão neutra, rig ou turntable calibrado, cabelo controlado sem
ocultar orelhas/linha capilar, 36 ângulos planejados.

**PROCESSO:** capturar cabeça e parte superior do pescoço em `000–350°`; manter olhar, mandíbula,
altura, distância e exposição; incluir topo e submento em tomadas extras; validar cobertura e
correspondência entre frames antes de encerrar a sessão.

**SAÍDA:** 36 vistas principais + extras de topo/submento, calibração, máscaras/proxies e
manifest da sessão.

**CRITÉRIO DE REPROVAÇÃO:** ângulo faltante; movimento de boca/olhos; foco fora da íris/pele; cabelo
oculta geometria; motion blur; exposição variável; rolling shutter severo; orelha/nuca ausente.

**DEPENDÊNCIAS:** Master Reference, identidade do performer confirmada, rig de captura e
calibração aprovados.

### 5.4 HALF BODY 360

**ENTRADA:** performer neutro da cabeça até quadril, braços levemente afastados, mãos visíveis,
roupa justa e matte para reconstrução corporal.

**PROCESSO:** capturar 36 ângulos com postura e respiração controladas; registrar ombros, axilas,
cotovelos, cintura, pescoço e continuidade cabeça-corpo; repetir frames com mão/tecido borrado.

**SAÍDA:** conjunto meio-corpo 360 calibrado, máscaras e manifest.

**CRITÉRIO DE REPROVAÇÃO:** braços colados ocultando torso; mãos cortadas; mudança de postura;
roupa larga/reflexiva; oclusão de pescoço/ombros; escala inconsistente com Master Reference.

**DEPENDÊNCIAS:** Identity Lock e Head 360 aprovados; marcações de piso/altura e roupa de captura.

### 5.5 FULL BODY 360

**ENTRADA:** performer em A-pose ou pose neutra definida, pés e mãos inteiros, roupa de captura,
36 ângulos e escala métrica.

**PROCESSO:** capturar da cabeça aos pés sem crop; manter distribuição de peso e posição dos
dedos; incluir vistas elevadas/baixas para ombros, topo da cabeça, sola/calçado; validar silhueta.

**SAÍDA:** conjunto full-body 360, medidas, silhuetas, máscaras, calibração e manifest.

**CRITÉRIO DE REPROVAÇÃO:** membros cortados; deslocamento no turntable; mudança de pose; lente
grande-angular deformando proporções; pés/axilas/entrepernas sem cobertura; escala ausente.

**DEPENDÊNCIAS:** Identity Lock, Head 360 e Half Body 360 aprovados; área de captura corporal.

### 5.6 CLOSE EYES

**ENTRADA:** macros dos dois olhos: frontal, três-quartos e perfil; olhos abertos, semicerrados e
fechados; chart de cor e luz polarizada/não polarizada.

**PROCESSO:** registrar íris, limbo, pupila, esclera, vasos, pálpebras, cílios, canto lacrimal e
tear line; separar olho esquerdo/direito; neutralizar reflexos só na derivação, preservando RAW.

**SAÍDA:** pacote bilateral de olhos, mapas/referências de íris e pálpebra, escala e manifest.

**CRITÉRIO DE REPROVAÇÃO:** catchlight estourado cobre íris; lente de contato não declarada; foco
atrás da íris; cor alterada; olho esquerdo espelhado para fabricar o direito; tear line ausente.

**DEPENDÊNCIAS:** Master Reference, captura macro calibrada e autorização para proximidade.

### 5.7 CLOSE SKIN

**ENTRADA:** macros de testa, bochechas, nariz, queixo, pescoço e áreas corporais representativas,
com luz cruzada polarizada e paralela.

**PROCESSO:** capturar albedo aparente e resposta especular; documentar poros, microdobras, pelos,
manchas e cicatrizes; remover iluminação apenas em derivado técnico, sem apagar microdetalhe.

**SAÍDA:** biblioteca de pele por região, pares polarizados, referência de escala e mapa de
características identitárias.

**CRITÉRIO DE REPROVAÇÃO:** maquiagem/filtro não documentado; sharpening/denoise destrutivo; pele
estourada; escala desconhecida; textura clonada que apaga assimetria ou marcas importantes.

**DEPENDÊNCIAS:** Master Reference, chart de cor, lente macro e protocolo de polarização.

### 5.8 CLOSE MOUTH

**ENTRADA:** macros de boca neutra fechada, repouso entreaberto, perfis e três-quartos, com lábios
hidratados de modo natural e sem gloss não documentado.

**PROCESSO:** capturar contorno, volume, sulcos, cantos, filtrum, vermelhão, contato labial e
assimetria; registrar variações sutis de compressão sem mudar identidade.

**SAÍDA:** pacote de lábios/boca externa, landmarks, referências de cor/roughness e manifest.

**CRITÉRIO DE REPROVAÇÃO:** batom/gloss altera material; foco insuficiente; sorriso substitui neutral;
cantos ocultos; contorno reconstruído por IA; cor incompatível com Master Reference.

**DEPENDÊNCIAS:** Master Reference, Close Skin e captura macro.

### 5.9 TEETH

**ENTRADA:** fotos intraorais seguras e não invasivas de incisivos, caninos e arcadas visíveis;
poses de sorriso/“teeth pose”; referência de oclusão normal.

**PROCESSO:** registrar forma, alinhamento, escala, cor relativa, translucidez, gengiva e mordida;
separar referência superior/inferior; usar um frame de dentes claro no Identity/Performance solve.

**SAÍDA:** referência dental aprovada, máscaras, medidas relativas e pose de dentes.

**CRITÉRIO DE REPROVAÇÃO:** dentes genéricos excessivamente brancos; arcada espelhada; mordida
inventada; saliva/reflexo oculta bordas; procedimento inseguro; escala incompatível com boca.

**DEPENDÊNCIAS:** Close Mouth, consentimento específico, protocolo higiênico e operador treinado.

### 5.10 TONGUE

**ENTRADA:** fotos seguras da língua em repouso e articulações visíveis, sem instrumento invasivo.

**PROCESSO:** capturar forma, volume, cor e superfície suficientes para planos internos de boca;
mapear limites de movimento necessários aos fonemas do benchmark.

**SAÍDA:** referência de língua e cavidade oral, material de referência e faixa de poses.

**CRITÉRIO DE REPROVAÇÃO:** cor/material artificial; geometria atravessa dentes; escala impossível;
captura desconfortável/insegura; ausência de referência para fonemas com língua visível.

**DEPENDÊNCIAS:** Teeth e Close Mouth aprovados; consentimento e protocolo seguro.

### 5.11 HAIR

**ENTRADA:** hairline descoberta, vistas 360 do penteado aprovado, macros de fios/raízes, cor sob
luz neutra e informação de densidade/direção.

**PROCESSO:** separar linha capilar, couro cabeludo, sobrancelhas, cílios, pelos faciais e cabelo;
mapear fluxo, partição, flyaways e variação de cor; criar referência para cards/strands sem usar
volume fotogramétrico do cabelo como geometria craniana.

**SAÍDA:** Hair Reference Pack com hairline, mapas de direção/densidade, grupos de groom e LODs
planejados.

**CRITÉRIO DE REPROVAÇÃO:** hairline ocultada/inventada; capacete sólido; transparência serrilhada;
cor única; ausência de flyaways; groom atravessa pele/orelha/roupa em pose neutra.

**DEPENDÊNCIAS:** Head 360, Close Skin e Identity Lock.

### 5.12 HANDS

**ENTRADA:** ambas as mãos em dorsal, palmar, laterais, punho, unhas e conjunto de poses (aberta,
relaxada, apontar, pinça, segurar produto e punho parcial).

**PROCESSO:** capturar 360 por mão, comprimentos/espessuras, articulações, unhas, veias e marcas;
registrar assimetria; validar contato com prop de escala conhecida.

**SAÍDA:** referências e meshes/texturas de mão esquerda/direita, poses de validação e medidas.

**CRITÉRIO DE REPROVAÇÃO:** mão espelhada; dedo/unha fundido; contagem errada; articulação colapsa;
punho não fecha; textura sem detalhe; pegada atravessa o produto.

**DEPENDÊNCIAS:** Full Body 360, Identity Lock e prop de teste dimensionado.

### 5.13 EXPRESSIONS

**ENTRADA:** neutral validado e lista dirigida: sorriso sutil/amplo, raiva, tristeza, surpresa,
nojo, medo, squint, brow up/down, jaw open, funnel, pucker, cheek puff, piscadas e fala PT-BR.

**PROCESSO:** capturar cada expressão do repouso ao ápice e retorno; manter cabeça/câmera
sincronizadas; selecionar frames canônicos; mapear assimetrias e poses corretivas necessárias.

**SAÍDA:** Expression Pack com vídeo/fotos sincronizados, frames apex, áudio quando aplicável,
pose labels e referência de amplitudes.

**CRITÉRIO DE REPROVAÇÃO:** neutral contaminado; expressão apenas caricata; falta de transição;
oclusão/motion blur; labels trocados; pose impossível de repetir; compressão que remove microgesto.

**DEPENDÊNCIAS:** Identity Lock, referências de olhos/boca/dentes/língua e direção do performer.

### 5.14 REFERENCE QUALITY GATE

**ENTRADA:** todos os pacotes das seções 5.1–5.13 e respectivos manifests.

**PROCESSO:** checagem automatizada de quantidade, hash, resolução, exposição, blur, metadata e
ângulos; revisão humana de cobertura, identidade, cor e consistência; montar contato completo e
lista objetiva de recapturas.

**SAÍDA:** relatório `REFERENCE_QG_vN` aprovado ou rejeitado, com cobertura por região, arquivos
faltantes, recapturas e assinatura do revisor.

**CRITÉRIO DE REPROVAÇÃO:** qualquer dependência rejeitada; lacuna angular relevante; cor/lente
inconsistente; asset sem origem/hash; ausência de detalhe P0 em olhos, boca, pele, cabelo ou mãos.

**DEPENDÊNCIAS:** estágios 5.1–5.13 completos; ferramenta de integridade e dois revisores
(técnico + identidade).

### 5.15 3D RECONSTRUCTION

**ENTRADA:** Reference Quality Gate aprovado, calibração de câmeras, máscaras e escala.

**PROCESSO:** resolver câmeras, gerar nuvem/mesh multiview e textura provisória; separar cabeça,
corpo, mãos e elementos problemáticos; alinhar à escala real; documentar software, parâmetros,
confiança e intervenções manuais. IA generativa pode criar candidato, nunca substituir evidência.

**SAÍDA:** reconstruction mesh em escala, câmeras resolvidas, textura provisória, confidence/
coverage maps e relatório de falhas.

**CRITÉRIO DE REPROVAÇÃO:** escala errada; drift; face suavizada; assimetrias perdidas; olhos/boca
fundidos; buracos em regiões P0; corpo incompatível com silhuetas; geometria alucinada sem marcação.

**DEPENDÊNCIAS:** Reference Quality Gate e pipeline multiview versionado.

### 5.16 MESH MASTER

**ENTRADA:** reconstruções aprováveis, Master Reference, Identity Lock e medidas.

**PROCESSO:** fundir melhores regiões; corrigir apenas artefatos; esculpir neutral anatômico;
preservar landmarks e assimetrias; separar globos oculares, dentes, língua e cavidade; alinhar
cabeça/corpo/mãos; comparar overlays em múltiplas vistas e registrar deltas.

**SAÍDA:** `MESH_MASTER_HI_vN` em escala real, neutral, componentes separados, relatório de
comparação e turntable clay.

**CRITÉRIO DE REPROVAÇÃO:** likeness depende da textura; proporções divergem do lock; neutral tem
expressão; smoothing elimina identidade; interseções/duplos; orientação/escala ambígua.

**DEPENDÊNCIAS:** 3D Reconstruction, Identity Lock, referências especializadas e artista de
character aprovado.

### 5.17 RETOPOLOGY

**ENTRADA:** Mesh Master aprovado e requisitos do MetaHuman From Custom Mesh.

**PROCESSO:** produzir malha de produção com edge flow para olhos, boca, nariz, mandíbula, pescoço,
ombros, mãos e articulações; criar UVs sem overlaps indevidos; projetar detalhes do high; validar
deformação antes de transferir materiais.

**SAÍDA:** mesh de produção versionado, UV sets, cages, bake maps, LOD plan e relatório de
deformação.

**CRITÉRIO DE REPROVAÇÃO:** edge loops quebram pálpebra/lábio; UV desperdiçada em região P0;
shrinkwrap muda silhueta; bake com cage artifact; non-manifold; tangentes/normais inconsistentes.

**DEPENDÊNCIAS:** Mesh Master, orçamento técnico por LOD e requisitos de importação MetaHuman.

### 5.18 METAHUMAN FROM CUSTOM MESH

**ENTRADA:** mesh de produção ou Mesh Master preparado, em pose/orientação/escala corretas, com
Identity Lock e texturas de referência.

**PROCESSO:** no MetaHuman Creator 5.8, usar Import → From Custom Mesh; atribuir source mesh;
conformar corpo e cabeça; aplicar correções técnicas; revisar correspondência; gerar personagem
MetaHuman e DNA/rig; não usar o preset como autoridade sobre a identidade.

**SAÍDA:** MetaHuman Character versionado, assets de conform, DNA/rig, relatório de deltas e
screenshots Reference × Viewport.

**CRITÉRIO DE REPROVAÇÃO:** identidade converge para preset genérico; pescoço/seam quebra; olhos,
boca ou crânio mudam; joints incompatíveis; processo não reproduzível; serviço de autorig falha.

**DEPENDÊNCIAS:** Retopology/Mesh Master aprovado, MetaHuman Creator 5.8 no Linux, conectividade
permitida ao serviço oficial de autorig e backup/duplicata do asset antes de conformar.

### 5.19 SKIN MASTER

**ENTRADA:** Close Skin, texturas da reconstrução, UV aprovado, mesh MetaHuman e referências de cor.

**PROCESSO:** construir albedo sem luz, normal/displacement de microdetalhe, roughness/specular,
subsurface e mapas de variação; reprojetar marcas identitárias; calibrar em iluminação neutra,
dura, suave e contraluz; evitar bake de sombra e wax look.

**SAÍDA:** conjunto `SKIN_MASTER_vN`, materiais Unreal, parâmetros por região e renders de esfera/
rosto sob cenas de teste.

**CRITÉRIO DE REPROVAÇÃO:** plástico/cera; poros uniformes; cor muda entre rosto/pescoço/corpo;
manchas somem; specular pintado no albedo; seam visível; detalhe quebra em close 4K.

**DEPENDÊNCIAS:** Close Skin, Retopology, MetaHuman From Custom Mesh e cenas de luz calibradas.

### 5.20 EYE MASTER

**ENTRADA:** Close Eyes, geometria ocular MetaHuman, captura bilateral e iluminação de referência.

**PROCESSO:** reproduzir íris esquerda/direita, pupila, limbo, esclera/vasos, córnea, umidade,
tear line, oclusão e pálpebras; calibrar refração/reflexo; testar olhar, piscada e extremos sem
sliding ou penetração.

**SAÍDA:** `EYE_MASTER_vN`, mapas e materiais bilaterais, tear line, poses/test renders.

**CRITÉRIO DE REPROVAÇÃO:** olho vítreo luminoso; íris espelhada; pupila/limbo fora de escala;
esclera branca pura; ausência de tear line; eyelid clipping; gaze divergente não intencional.

**DEPENDÊNCIAS:** Close Eyes, MetaHuman mesh/rig preliminar e Skin Master.

### 5.21 MOUTH MASTER

**ENTRADA:** Close Mouth, Teeth, Tongue, cavidade do Mesh Master e rig facial preliminar.

**PROCESSO:** modelar/ajustar lábios, gengiva, dentes individuais relevantes, língua e cavidade;
criar materiais de umidade/translucidez; validar oclusão, fechamento labial, jaw open e fonemas
PT-BR em luz de close.

**SAÍDA:** `MOUTH_MASTER_vN`, meshes, materiais, poses corretivas e turntable interno.

**CRITÉRIO DE REPROVAÇÃO:** dentes genéricos/brancos; língua plana; boca preta vazia; gengiva sem
volume; interpenetração; lábio não fecha; popping; saliva/wetness excessiva ou ausente.

**DEPENDÊNCIAS:** Close Mouth, Teeth, Tongue, MetaHuman From Custom Mesh e Expression Pack.

### 5.22 GROOM

**ENTRADA:** Hair Reference Pack, scalp/hairline, sobrancelhas, cílios, pelos faciais e mesh final.

**PROCESSO:** criar guides/strands/cards por grupo; ajustar densidade, direção, clumping, frizz,
flyaways e variação de cor; bind ao scalp/face; configurar LOD e simulação; testar vento, cabeça e
ombros sem colisão.

**SAÍDA:** `GROOM_MASTER_vN`, bindings, materiais, LODs, physics settings e renders 360/close.

**CRITÉRIO DE REPROVAÇÃO:** efeito capacete; scalp visível indevido; hairline artificial; cílios/
sobrancelhas genéricos; flicker/aliasing; clipping; simulação instável; perda P0 em close.

**DEPENDÊNCIAS:** Hair, Skin Master, mesh/rig e collision proxies aprovados.

### 5.23 CLOTHING

**ENTRADA:** corpo final, medidas, roupa real ou design aprovado, tecidos escaneados/referenciados e
poses do benchmark.

**PROCESSO:** modelar/patronar, definir espessura, materiais e costuras; skin/simular; configurar
colisão e LOD; testar braços, sentar, apontar, segurar produto e vento; preservar contato natural.

**SAÍDA:** `CLOTHING_MASTER_vN`, garments, texturas, material, sim/collision config, LODs e testes.

**CRITÉRIO DE REPROVAÇÃO:** clipping; tecido sem espessura; estiramento de textura; dobra plástica;
sim explode; roupa altera silhueta identitária sem aprovação; interseção com cabelo/mãos/produto.

**DEPENDÊNCIAS:** Full Body, mesh/rig, corpo de colisão, referências de tecido e motion tests.

### 5.24 RIG

**ENTRADA:** MetaHuman conformado, DNA, meshes/materials finais, Expression Pack, hands, groom e
clothing.

**PROCESSO:** validar skeleton, RigLogic/face rig, skin weights, joints auxiliares, correctives,
Control Rig, olhos/mandíbula/língua/dedos; retarget; aplicar range-of-motion e áudio PT-BR;
registrar versão do rig e compatibilidade com animações.

**SAÍDA:** `RIG_MASTER_vN`, DNA/skeleton/Control Rig, corrective shapes, test animations,
compatibility manifest e relatório de deformação.

**CRITÉRIO DE REPROVAÇÃO:** perda de volume; eyelid/lip sliding; jaw/teeth mismatch; dedo colapsa;
neck/shoulder seam; groom/roupa perdem bind; curves ausentes; dependência oculta de Windows.

**DEPENDÊNCIAS:** MetaHuman From Custom Mesh, Skin/Eye/Mouth Masters, Groom, Clothing, Hands e
Expressions aprovados.

### 5.25 FINAL AVATAR QUALITY GATE

**ENTRADA:** avatar completo, Master Reference/Identity Lock, rig, materiais, groom, clothing,
animações de teste, áudio PT-BR e cenas de luz/câmera bloqueadas.

**PROCESSO:** executar bateria reproduzível em 4K: neutral 360, close estático, close falado de
8 s+, expressão/transição, gaze/piscada, boca/dentes/língua, mãos com produto, meio-corpo,
full-body e movimento com roupa/cabelo; comparar lado a lado e por overlay Reference × Render;
registrar métricas, defeitos, severidade e aprovadores.

**SAÍDA:** pacote `FINAL_AVATAR_QG_vN` com renders, vídeo, manifests, logs sanitizados,
comparações, checklist, decisão `APPROVED` ou `REJECTED` e lista de correções.

**CRITÉRIO DE REPROVAÇÃO:** qualquer falha P0: identidade não reconhecível/diferente; uncanny eyes;
pele plástica; hairline/groom artificial; lip-sync ou articulação quebrada; dentes/língua falsos;
interpenetração; mãos deformadas; popping/flicker; rig quebrando; close de 8 s não sustenta realismo;
asset sem hash/proveniência; revisão apenas em viewport baixa, sem render final.

**DEPENDÊNCIAS:** todos os estágios 5.1–5.24 aprovados, GPU/Unreal/MetaHuman operacionais, cena de
benchmark versionada e revisão técnica + identidade + direção criativa.

## 6. Matriz de falhas P0

| Categoria | Falha bloqueante |
|---|---|
| Identidade | rosto/corpo reconhecidamente diferente do Identity Lock |
| Pele | cera/plástico, cor errada, poro repetitivo, seam ou detalhe destruído |
| Olhos | gaze morta, íris falsa, tear line ausente, clipping ou piscada mecânica |
| Boca | lip-sync incorreto, lábio flutuante, dentes genéricos, língua/cavidade falsas |
| Cabelo | capacete, hairline inventada, flicker grave, clipping ou física instável |
| Corpo | proporção errada, pescoço/ombro quebrado, deformação ou foot sliding grave |
| Mãos | anatomia/contagem errada, colapso de dedo ou contato impossível com produto |
| Roupa | clipping recorrente, simulação explosiva ou tecido incompatível com referência |
| Performance | expressão robótica, falta de microvariação, olhos/cabeça desconectados da fala |
| Pipeline | artefato ausente, não reproduzível, sem versão/hash ou dependência não declarada |

Uma falha P0 reprova o gate mesmo que as demais categorias estejam boas.

## 7. Teste mínimo do avatar aprovado

O pacote de aprovação precisa conter, no mínimo:

1. frame frontal, perfis e três-quartos em iluminação neutra;
2. turntable 360 de cabeça, meio-corpo e corpo inteiro;
3. close 4K de 8 segundos ou mais, sem corte que esconda defeitos;
4. fala PT-BR com bilabiais, labiodentais, língua visível e mudança emocional;
5. olhos câmera → fora → retorno, com piscadas e micro-saccades naturais;
6. neutral → micro sorriso → expressão intensa → neutral sem popping;
7. mão apontando e segurando produto com escala conhecida;
8. cabelo e roupa sob movimento e contraluz;
9. três cenários de luz: suave, dura lateral e contraluz;
10. relatório Reference × Render, versões, hashes, métricas e decisão assinada.

## 8. Critério de promoção no Avatar Registry

```text
DRAFT
  → REFERENCES_CAPTURED       somente após Reference Quality Gate
  → IDENTITY_LOCKED           somente com aprovação registrada
  → MESH_READY                somente após Mesh Master + Retopology
  → RIGGED                    somente após MetaHuman From Custom Mesh + Rig
  → LOOKDEV_READY             somente após Skin/Eye/Mouth/Groom/Clothing
  → QUALITY_REVIEW            somente com benchmark completo
  → PRODUCTION_READY          somente após Final Avatar Quality Gate APPROVED
```

Não pular estados. Rejeição volta ao primeiro estágio causador e cria nova versão dos derivados;
não apaga evidência nem reescreve o Identity Lock aprovado.

## 9. Fontes oficiais

- [MetaHuman 5.8 Release Notes — Epic Games](https://dev.epicgames.com/documentation/metahuman/metahuman-5-8-release-notes-in-unreal-engine)
- [MetaHuman Creator Import Tools — Epic Games](https://dev.epicgames.com/documentation/metahuman/metahuman-creator-import-tools-in-unreal-engine)
- [From Mesh / Mesh to MetaHuman — Epic Games](https://dev.epicgames.com/documentation/metahuman/from-mesh)
- [Create a MetaHuman Identity — Epic Games](https://dev.epicgames.com/documentation/metahuman/create-a-metahuman-identity-in-unreal-engine)
- [MetaHuman Animator — Epic Games](https://dev.epicgames.com/documentation/metahuman/metahuman-animator-in-unreal-engine)

## 10. Ordem de execução final

**MASTER REFERENCE → IDENTITY LOCK → HEAD 360 → HALF BODY 360 → FULL BODY 360 →
CLOSE EYES → CLOSE SKIN → CLOSE MOUTH → TEETH → TONGUE → HAIR → HANDS → EXPRESSIONS →
REFERENCE QUALITY GATE → 3D RECONSTRUCTION → MESH MASTER → RETOPOLOGY →
METAHUMAN FROM CUSTOM MESH → SKIN MASTER → EYE MASTER → MOUTH MASTER → GROOM →
CLOTHING → RIG → FINAL AVATAR QUALITY GATE**
