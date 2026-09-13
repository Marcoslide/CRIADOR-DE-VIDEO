"""Avatar Factory Control Plane — Identity Lock, referências 360°/especializadas, QA
determinístico, quality gates e histórico imutável de transição de status.

Evolui o Avatar Registry (`core/avatars`) sem alterá-lo: este pacote é o consumidor dos
subsistemas que a fundação da Fase 3 deixou explicitamente para depois (ver docstring de
`dhf_avatars.models` e `docs/ARCHITECTURE.md` seção "Avatar (seção 12)"). Nenhuma
reconstrução 3D, MetaHuman ou render acontece aqui — isso depende da RTX 4090 real e é
propositalmente NOT_GENERATED/NOT_TESTED/BLOCKED até lá.
"""
