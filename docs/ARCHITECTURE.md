# VANDA — Documentação Técnica

## O que é o VANDA?

O VANDA é uma plataforma de nutrigenética que extrai, classifica e disponibiliza relações entre **variantes genéticas (SNPs)**, **genes**, **doenças** e **alimentos** a partir de literatura científica do PubMed e do GWAS Catalog.

**Ponto-chave do projeto**: Automatizar a extração de conhecimento nutrigenético que hoje está disperso em milhares de artigos científicos, tornando-o acessível para profissionais de saúde e pesquisadores. A plataforma responde perguntas como: *"Quais variantes genéticas influenciam a resposta do organismo à manteiga?"* — conectando SNPs, genes, doenças e alimentos em uma interface consultável.

**Ideia central**: Pessoas diferentes respondem de forma diferente aos mesmos nutrientes por causa de suas variações genéticas (SNPs). O VANDA busca mapear essas relações automaticamente.

**Diferencial**: Nenhuma outra plataforma conecta variantes genéticas a **alimentos** específicos. O GWAS Catalog, DisGeNET e outros param na associação gene-doença. O VANDA fecha o triângulo SNP → Doença → Alimento via FooDB.

---

## Arquitetura do Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                    FONTES DE DADOS                       │
├──────────────┬──────────────┬──────────────┬────────────┤
│ NCBI/PubMed  │ GWAS Catalog │   BioRED     │   TBGA     │
│ (artigos)    │ (associações │  (600 docs   │ (200K+     │
│              │  com OR)     │  anotados)   │ gene-doença│
└──────┬───────┴──────┬───────┴──────┬───────┴─────┬──────┘
       │              │              │             │
       ▼              │              ▼             ▼
┌──────────────┐      │     ┌────────────────────────────┐
│ Etapa 1:     │      │     │ Etapa 2: Treino            │
│ Download     │      │     │ BioRED + TBGA + GWAS       │
│ SNPs+Artigos │      │     │ → PubMedBERT fine-tuned    │
│ (lib/entrez) │      │     │ F1-macro: 0.8465           │
└──────┬───────┘      │     └─────────────┬──────────────┘
       │              │                   │
       ▼              │                   ▼
┌──────────────┐      │     ┌──────────────────────────┐
│ Etapa 3:     │      │     │ Etapa 4: NER + Classify  │
│ GWAS Import  │◄─────┘     │ FASE A: HunFlair2 (GPU)  │
│ (odds ratio, │            │   → extrai entidades     │
│  p-value)    │            │ FASE B: PubMedBERT (GPU) │
└──────┬───────┘            │   → classifica relações  │
       │                    └─────────────┬────────────┘
       │                                  │
       ▼                                  ▼
┌─────────────────────────────────────────────────────────┐
│                    database.sqlite                       │
│  snps (261K) │ articles (6K) │ foods (3.3M) │ snp_preds │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    FastAPI (API REST)                     │
│  /search  │  /snp/{id}  │  /gene/{id}  │  /food/{name} │
│  /evidence/{id}                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Pipeline de Dados — Passo a Passo

### Etapa 1: Coleta de Dados (`download/main.py` / `run_all.py`)

**O que faz**: Busca todos os SNPs com artigos citados no PubMed e baixa os metadados dos artigos.

**Como funciona**:
1. Consulta o NCBI Entrez com o filtro `snp_pubmed_cited[Filter] OR snp_pubmed[Filter]`
2. Para cada SNP encontrado, busca o HGVS (nomenclatura de mutação) e o gene associado
3. Usa `Entrez.elink()` para ligar cada SNP aos seus artigos PubMed
4. Filtra artigos por nutrigenética usando filtro expandido:
   - **16 termos MeSH**: Nutrigenomics, Nutrigenetics, Diet, Vitamins, Fatty Acids, Minerals, Folic Acid, Vitamin D, Caffeine, Food, etc.
   - **8 termos textuais** no título/abstract: nutrigenetic, nutrigenomic, diet-gene, personalized nutrition, etc.
5. Baixa título e abstract de cada artigo filtrado
6. Salva tudo no SQLite: tabelas `snps`, `articles`, `snp_articles`
7. Rate limit: 3 req/s com `NCBIRateLimiter` thread-safe

**Saída**: ~261K SNPs, ~6K artigos filtrados por nutrigenética, ~30K relações SNP-artigo

**Dependências**: BioPython (Entrez API), requests

### Etapa 2: Treino do Modelo (`training/biored_data.py` + `training/train.py`)

**O que faz**: Prepara dados de treino e fine-tuna PubMedBERT para classificar relações gene-doença.

**Dados de treino (3 fontes combinadas)**:

| Fonte | Exemplos | Direções | Ano |
|---|---|---|---|
| BioRED (NCBI) [2] | ~8.6K | beneficial, harmful, neutral, no_relation | 2022 |
| TBGA (DisGeNET) [3] | ~150K | therapeutic→beneficial, genomic_alterations→harmful, biomarker→neutral | 2022 |
| GWAS Catalog | ~20K | Derivado de odds ratio (OR>1.2→harmful, OR<0.8→beneficial) | Atualizado |

**Data augmentation**: Substituição de sinônimos nas classes minoritárias (beneficial). Exemplo: "protective" ↔ "reduces risk" ↔ "inversely associated".

**Balanceamento**: Classes limitadas a max 3x a menor classe para evitar viés.

**Dataset final**: ~31.9K exemplos balanceados (train: 25.5K, dev: 3.2K, test: 3.2K)

**Modelo**: `microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext` [1]
- Pré-treinado do zero em PubMed (não adaptado do BERT geral, Gu et al. 2021)
- Fine-tuned com WeightedRandomSampler, AdamW (lr=2e-5), linear warmup
- Input com entity markers seguindo o formato BioRED [2]: `"The @rs1801133@ variant reduced risk of #neural tube defects#"`
- 4 classes: beneficial (0), harmful (1), neutral (2), no_relation (3)

**Resultados do treino (10 epochs, GTX 1060 6GB)**:
```
Epoch 1:  F1 = 0.7621
Epoch 3:  F1 = 0.8237
Epoch 6:  F1 = 0.8408
Epoch 10: F1 = 0.8465 ← melhor modelo
```

**Contexto**: F1=0.8465 está acima do SOTA reportado pelo BioREx (NCBI, 2023: 0.796) e na faixa dos melhores da competição BioCreative VIII (2024: ~0.82-0.85). Limite teórico (concordância inter-anotador): ~0.90-0.92.

### Etapa 3: Importação GWAS Catalog (`training/gwas_import.py`)

**O que faz**: Importa associações SNP-doença curadas do GWAS Catalog com odds ratios reais.

**Como funciona**:
1. Baixa o TSV completo do GWAS Catalog [4] (~701MB, 1.18M associações, Sollis et al. 2023)
2. Filtra por nutrigenética (mesmos termos MeSH/texto da Etapa 1)
3. Filtra por significância genômica (p-value < 5×10⁻⁸)
4. Separa OR de BETA (heurística: valores < 0.3 são BETA, ignorados)
5. Converte odds ratio para direção:
   - OR > 1.2 → harmful
   - OR < 0.8 → beneficial
   - 0.8 ≤ OR ≤ 1.2 → neutral
6. Salva no `snp_preds` com `model_version='gwas-catalog'`, odds_ratio e p_value

**Resultado**: ~5,194 associações nutrigenéticas (220 beneficial, 1412 harmful, 3562 neutral)

**Vantagem**: Dados curados por especialistas com evidência estatística real (não classificação ML).

### Etapa 4: NER + Classificação (`run_all.py`)

**O que faz**: Para cada artigo baixado, extrai entidades e classifica relações em duas fases.

**FASE A — NER (HunFlair2, GPU)**:
1. Carrega HunFlair2 [5] na GPU (se VRAM > 1GB, Sänger et al. 2024)
2. Para cada artigo: segmenta em janelas de 3 frases
3. Extrai entidades em batch (`tagger.predict(sentences, mini_batch_size=32)`)
4. Para cada par (SNP/Gene × Disease), cria input com entity markers
5. Libera HunFlair2 da GPU (`torch.cuda.empty_cache()`)

**Velocidade**: ~2.2 artigos/s na GTX 1060 GPU (~4x mais rápido que CPU)

**FASE B — Classificação (PubMedBERT, GPU)**:
1. Carrega PubMedBERT na GPU (VRAM agora livre do NER)
2. Tokeniza por batch (não pré-tokeniza tudo para evitar OOM na RAM)
3. Classifica em batches de 128 com mixed precision (`torch.amp.autocast`)
4. Filtra: descarta `no_relation` e `confidence < min_confidence`
5. Salva no `snp_preds` com confidence e model_version

**Por que duas fases**: HunFlair2 + PubMedBERT juntos cabem na GPU (testado), mas separar em fases permite batch_size maior na Fase B (128 vs 32) e evita fragmentação de VRAM.

**Tempo total (GTX 1060, 6K artigos)**: ~45 min NER + ~90 min classify = ~2.2 horas

### Etapa 5: Integração com Alimentos

**O que faz**: Conecta genes a alimentos usando a base FooDB.

A tabela `foods` (3.3M registros, pré-importada do FooDB [7]) mapeia cada gene aos alimentos que contêm nutrientes metabolizados por esse gene. O JOIN com `snp_preds` via `gene_info` permite responder: *"Para este alimento, quais SNPs são benéficos/prejudiciais?"*

### Etapa 6: Validação e Controle de Qualidade dos Dados

A saída do pipeline de classificação contém ruídos inerentes à extração automática de texto. Um processo de validação em múltiplas camadas foi aplicado para garantir a qualidade e confiabilidade dos dados apresentados na plataforma.

#### 6.1 — Normalização Inicial (`processing/normalize_db.py`)

Primeira camada de limpeza nos dados brutos do pipeline:

1. **Normalização de case**: Unificação de variações tipográficas ("obesity" / "Obesity" / "OBESITY" → "Obesity")
2. **Merge de sinônimos**: Mapeamento de abreviações e nomes alternativos para termos canônicos ("CRC" → "Colorectal Cancer", "T2D" → "Type 2 Diabetes", "obese" → "Obesity")
3. **Deduplicação**: Remoção de registros duplicados com mesmo pmid+snp+disease+direction
4. **Remoção de dados legacy**: Exclusão dos dados do pipeline antigo (BioBERT + weak labels), que tinha F1 ~0.50 e produzia classificações ruidosas

**Resultado**: 508K registros → **64.9K**

#### 6.2 — Limpeza de Entidades Incorretas (`processing/cleanup_pipeline.py`)

Identificação e remoção de erros sistemáticos do NER e do classificador:

1. **Genes classificados como SNPs**: O HunFlair2 NER extraía nomes de genes (SLC6A3, DOPAMINE TRANSPORTER, DAT1) e os salvava no campo `snp` do banco de dados. Como genes não são variantes genéticas, esses registros produziam associações sem base biológica. Critério: campo `snp` que não inicia com "RS". **43K registros removidos.**

2. **Doenças fora do escopo nutrigenético**: O filtro MeSH incluía "Pharmacogenetics", capturando artigos sobre interações droga-gene (não alimento-gene). Isso gerava associações como "Beer → Cocaine Addiction" (via gene SLC6A3 e um artigo sobre disulfiram). Removidas doenças psiquiátricas, infecciosas e farmacogenéticas sem relação com nutrição: Cocaine Addiction, Schizophrenia, HIV, Epilepsy, Tuberculosis, etc. **5K registros removidos, "Pharmacogenetics" removido do filtro MeSH.**

3. **Predições contraditórias**: O mesmo par SNP+doença classificado com direções diferentes em janelas de texto distintas (ex: rs1229984 + Alcohol Dependence classificado como "harmful" em uma frase e "neutral" em outra). Resolução: manter apenas a predição com maior confidence. **4K registros removidos.**

4. **Entidades genéricas**: Doenças extraídas pelo NER que não representam condições específicas ("disease", "tumor", "cancer" sem qualificador). **1.5K registros removidos.**

**Resultado**: 64.9K → **15.8K**

#### 6.3 — Normalização de Nomenclatura GWAS (`processing/normalize_gwas_diseases.py`)

O GWAS Catalog utiliza nomenclatura descritiva com qualificadores experimentais que dificultam o cruzamento com os dados da IA:

- "Type 2 Diabetes (adjusted for BMI)" → **Type 2 Diabetes**
- "Coronary Artery Disease (myocardial Infarction, Percutaneous Transluminal Coronary Angioplasty...)" → **Coronary Artery Disease**
- "Body mass index" → **Obesity**

Estudos compostos/pleiotrópicos removidos ("Psoriasis or Type 2 Diabetes (trans-disease Meta-analysis)").

**Resultado**: 495 → **342 doenças únicas no GWAS**

#### 6.4 — Expansão de Siglas Clínicas

Siglas reconhecidas expandidas para nomes completos legíveis:

| Sigla | Expansão |
|---|---|
| DM2, T2DM | Type 2 Diabetes |
| HTN, EH | Hypertension |
| CRC, Mcrc | Colorectal Cancer |
| Mets, MetS | Metabolic Syndrome |
| AMD | Age-Related Macular Degeneration |
| NASH, MASH | Non-Alcoholic Fatty Liver Disease |
| GDM | Gestational Diabetes |
| NTD, Ntds | Neural Tube Defects |

Siglas não reconhecidas (ZSDS, NSCPO, EAP, HFU, etc.) removidas por não serem interpretáveis por usuários da plataforma. **~3K registros removidos.**

**Resultado final**: 15.8K → **12.5K registros**

#### 6.5 — Validação Cruzada GWAS ↔ IA

Após normalização, **134 pares SNP+Disease** existem em ambas as fontes (GWAS Catalog e PubMedBERT). Análise de concordância:

| Concordância | Pares | % |
|---|---|---|
| **Mesma direção** | 50 | 37% |
| Direções diferentes | 84 | 63% |

Detalhamento da discordância:

| GWAS | IA | Pares | Explicação |
|---|---|---|---|
| harmful | harmful | 38 | Concordância total — evidência mais forte |
| neutral | neutral | 12 | Concordância total |
| neutral | harmful | 86 | GWAS: OR próximo de 1 (efeito pequeno); IA: texto diz "risk" |
| harmful | neutral | 12 | GWAS: OR significativo; IA: classificou como neutro |
| beneficial | harmful | 2 | Discordância total — requer revisão manual |

A discordância principal (GWAS "neutral" vs IA "harmful") reflete perspectivas metodológicas diferentes: o GWAS mede o **tamanho do efeito** (OR próximo de 1.0 = pequeno → neutral), enquanto a IA interpreta a **linguagem do artigo** (que pode dizer "increased risk" mesmo para efeitos pequenos).

#### Resumo do Processo de Qualidade

| Etapa | Registros removidos | Registros restantes |
|---|---|---|
| Saída bruta do pipeline | — | 508K |
| Remoção legacy + dedup | 443K | 64.9K |
| Genes como SNPs | 43K | ~22K |
| Doenças não-nutrigenéticas | 5K | ~17K |
| Duplicatas contraditórias | 4K | ~13K |
| Doenças genéricas/lixo | 1.5K | ~12K |
| Siglas não reconhecidas | 3K | 15.8K* |
| Normalização + expansão siglas | — | 12.5K |
| Validação relevância food→article | 1.2K | **11.3K** |

*Nota: as etapas não são estritamente sequenciais — alguns registros são afetados por múltiplas regras.

#### 6.6 — Validação de Relevância Food→Article (`processing/validate_food_relevance.py`)

O FooDB mapeia genes a **todos** os alimentos que contêm qualquer composto metabolizado por aquele gene. Isso gera associações indiretas clinicamente irrelevantes. Exemplo: Beer aparecia ligado a "COVID-19 severity" porque o gene NADSYN1 (síntese de vitamina D) está listado no FooDB para cerveja, e um artigo sobre vitamina D e COVID mencionava esse gene.

**Solução em duas camadas**:

1. **Filtragem no banco** (`validate_food_relevance.py`): Remove predições da IA cujo abstract não menciona nenhum termo nutricional (diet, nutrient, vitamin, etc.). Remove artigos puramente farmacogenéticos. **1.2K predições removidas.**

2. **Filtragem em tempo real na API** (`app/routers/variants.py`): Ao buscar um alimento, verifica se o abstract de cada artigo realmente menciona o alimento ou termos relacionados (ex: buscar "Beer" → verifica se abstract contém "beer", "alcohol", "ethanol", "drink"). Associações do GWAS sempre mantidas (curadas manualmente).

**Resultado**: 12.5K → **11.3K registros**. Associações como Beer→COVID-19, Beer→Cocaine Addiction não aparecem mais na plataforma.

**Limitação documentada**: A associação food→gene via FooDB é bioquímica, não clínica. Um gene pode metabolizar compostos presentes em milhares de alimentos, mas a relevância nutricional depende da quantidade e do contexto. A filtragem por abstract reduz falsos positivos mas não elimina completamente associações indiretas.

**Scripts de validação**:
```bash
python processing/normalize_db.py --db database.sqlite --remove-legacy
python processing/cleanup_pipeline.py --db database.sqlite
python processing/normalize_gwas_diseases.py --db database.sqlite
python processing/validate_food_relevance.py --db database.sqlite
```

---

## Banco de Dados

### Tabelas principais (`database.sqlite`)

| Tabela | Descrição | ~Registros |
|---|---|---|
| `snps` | SNP ID, HGVS, gene associado | 261K |
| `articles` | PMID, título, abstract do PubMed | 6K |
| `snp_articles` | Relação N:N entre SNPs e artigos | 30K |
| `foods` | Gene → alimento (FooDB) | 3.3M |
| `snp_preds` | Predições: SNP, doença, direção, confidence | ~12.5K |
| `pipeline_state` | Estado do pipeline incremental | < 10 |
| `_migrations` | Migrações de schema aplicadas | ~4 |

### Schema do `snp_preds`
```sql
CREATE TABLE snp_preds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pmid INTEGER NOT NULL,          -- rastreabilidade ao artigo original
    title TEXT,
    snp TEXT NOT NULL,              -- ex: RS1801133
    disease TEXT NOT NULL,          -- ex: Type 2 Diabetes
    direction TEXT NOT NULL,        -- beneficial, harmful, neutral
    confidence REAL NOT NULL,       -- 0.0 a 1.0 (softmax do modelo ou derivado do OR)
    model_version TEXT,             -- pubmedbert-biored-v1, gwas-catalog, legacy-biobert-v1
    odds_ratio REAL,                -- OR do GWAS (NULL para predições ML)
    p_value REAL,                   -- p-value do GWAS (NULL para predições ML)
    study_info TEXT,                -- tamanho da amostra do GWAS
    created_at TIMESTAMP
);
```

### Fontes de dados no `snp_preds`

| model_version | Fonte | Confidence | Qualidade |
|---|---|---|---|
| `gwas-catalog` | GWAS Catalog (curado, odds ratio real) | Derivada do OR | Alta (evidência estatística) |
| `pubmedbert-biored-v1` | HunFlair2 NER + PubMedBERT RE (F1=0.85) | Softmax probability | Média-alta |

**Nota**: Dados legacy (`legacy-biobert-v1`) foram removidos após re-processamento com o novo pipeline. O banco contém apenas predições de alta qualidade.

---

## API REST (FastAPI)

### Endpoints

| Endpoint | Método | Descrição |
|---|---|---|
| `/search/?query=MTHFR` | GET | Busca SNPs por gene/keyword |
| `/snp/{snp_id}` | GET | Detalhes de um SNP com tópicos de doença |
| `/gene/{gene_id}` | GET | Informações do gene com artigos agrupados |
| `/snps/food-analize/{food}` | GET | Análise de alimento: genes, SNPs, direções, confidence, odds_ratio |
| `/evidence/{pred_id}` | GET | Rastreabilidade: artigo original + SNP + confidence |
| `/evidence/pmid/{pmid}` | GET | Verificar cadeia de evidência por PMID |
| `/enrich/frequency/{rsid}` | GET | Frequência populacional por etnia (gnomAD) |
| `/enrich/clinvar/{rsid}` | GET | Significância clínica e condições (ClinVar) |
| `/enrich/compounds/{gene}` | GET | Compostos nutricionais do gene (FooDB) |
| `/enrich/food-detail/{food}` | GET | Gene → alimento → compostos → associações |
| `/enrich/snp-complete/{rsid}` | GET | Tudo: frequência + ClinVar + predições + alimentos |
| `/disease/{name}` | GET | Análise de doença: SNPs, genes, alimentos relacionados |
| `/info/food/{name}` | GET | Descrição de alimento/nutriente (MeSH) |
| `/info/disease/{name}` | GET | Descrição de doença (MeSH) |
| `/suggest?q=X` | GET | Autocomplete: retorna SNPs, genes, doenças, alimentos que existem no banco |
| `/health` | GET | Health check |

### Integrações Externas

| Integração | Endpoint | Fonte | Dado |
|---|---|---|---|
| **gnomAD** [6] | `/enrich/frequency/{rsid}` | gnomAD GraphQL API v4 (Karczewski et al. 2020) | Frequência alélica por população (African, European, East Asian, South Asian, Latino, etc.) |
| **ClinVar** [11] | `/enrich/clinvar/{rsid}` | NCBI Entrez (Landrum et al. 2018) | Significância clínica (pathogenic, benign, risk factor), condições associadas, review status |
| **FooDB** | `/enrich/compounds/{gene}` | Banco local (tabela `foods`) | Alimentos com compostos metabolizados pelo gene, rankeados por quantidade |

### Endpoint SNP Completo

O endpoint `/enrich/snp-complete/{rsid}` retorna todas as informações de um SNP em uma única chamada:

```json
{
  "rsid": "rs9939609",
  "gene": "FTO",
  "frequency": {
    "global_frequency": 0.423,
    "populations": {
      "African": {"frequency": 0.52},
      "Non-Finnish European": {"frequency": 0.45},
      "East Asian": {"frequency": 0.15}
    }
  },
  "clinvar": {
    "clinical_significance": "risk factor",
    "conditions": ["Obesity", "Type 2 Diabetes"]
  },
  "predictions": [
    {"disease": "Obesity", "direction": "harmful", "confidence": 0.91, "source": "pubmedbert-biored-v1"},
    {"disease": "Type 2 Diabetes", "direction": "harmful", "confidence": 0.87, "source": "gwas-catalog", "odds_ratio": 1.67}
  ],
  "foods": [
    {"food": "Butter", "amount": 49.55, "unit": "uM"},
    {"food": "Cheese", "amount": 38.2, "unit": "mg/100g"}
  ]
}
```

### Modelos usados na API

| Modelo | Uso | Carregamento |
|---|---|---|
| HunFlair2 | NER de doenças nos endpoints /snp e /gene | Lazy loading |
| Falconsai/medical_summarization | Sumarização de abstracts | Lazy loading |

---

## Script Unificado (`run_all.py`)

Roda todo o pipeline de uma vez com tratamento de erros, retry e progresso.

```bash
# Pipeline completo (treino + download + classificação)
python run_all.py

# Só classificação (modelo já treinado, artigos já baixados)
python run_all.py --skip-training --skip-download

# Com filtro de confiança
python run_all.py --min-confidence 0.7

# Opções
python run_all.py --epochs 10 --batch-size 128 --min-confidence 0.5
```

### Etapas do `run_all.py`

| Etapa | Flag para pular | Descrição |
|---|---|---|
| 0. Migrações | Sempre roda | Cria/atualiza tabelas |
| 1. Datasets | `--skip-training` | Baixa BioRED + TBGA + GWAS, combina e balanceia |
| 2. Treino | `--skip-training` | Fine-tune PubMedBERT (10 epochs) |
| 2.5 GWAS | Sempre roda | Importa GWAS Catalog para snp_preds |
| 3. Download | `--skip-download` | Baixa artigos do NCBI |
| 4. NER + Classify | Sempre roda | Fase A (NER GPU) + Fase B (Classify GPU) |
| 5. Relatório | Sempre roda | Estatísticas finais |

### Proteções

- **Ctrl+C**: Graceful shutdown via `signal.SIGINT`
- **OOM GPU (treino)**: Reduz batch_size automaticamente (16 → 8 → 4)
- **OOM GPU (classify)**: Divide batch ao meio recursivamente
- **OOM RAM**: Tokenização por batch (não pré-tokeniza tudo)
- **Rede NCBI**: Retry com backoff, rate limiting 3 req/s
- **Incremental**: `pipeline_state.last_predicted_rowid` evita re-processar
- **Log**: Tudo salvo em `vanda_pipeline_YYYYMMDD_HHMMSS.log`

### Docker

```bash
# Build da imagem
docker build -f Dockerfile.pipeline -t vanda-pipeline .

# Rodar com GPU
docker run --gpus all --rm --memory=8g \
    -v $(pwd):/app -w /app --env-file .env \
    vanda-pipeline python run_all.py
```

---

## FAQ — Decisões Técnicas

### Por que não usar LLMs (ChatGPT, Claude) para classificação?

- **Custo**: Processar ~100K artigos custaria $15-30+ por execução
- **Velocidade**: Muito mais lento que modelos locais
- **Dependência externa**: API pode mudar, ficar offline, ou mudar preços
- **Reprodutibilidade**: Resultados podem variar entre versões do modelo

**Decisão**: Modelos locais (PubMedBERT) para independência, reprodutibilidade e custo zero.

### Por que PubMedBERT e não BioBERT?

PubMedBERT [1] (2021) é pré-treinado **do zero** em PubMed com vocabulário biomédico nativo. BioBERT v1.1 [8] (2019) é adaptado do BERT geral. Gu et al. demonstraram que o pré-treino from-scratch em domínio específico supera a adaptação de modelos genéricos em múltiplos benchmarks biomédicos. Mesma arquitetura, mesma velocidade, melhor performance.

### Por que BioRED + TBGA e não só weak labeling?

Weak labeling por keywords tinha ~50% de acurácia (testado empiricamente). BioRED [2] (600 abstracts anotados por especialistas do NCBI, Luo et al. 2022) + TBGA [3] (200K+ pares gene-doença do DisGeNET, Marchesin & Silvello 2022) fornecem dados de qualidade muito superior. A abordagem de combinar datasets heterogêneos segue o framework BioREx [9] do NCBI. Resultado: F1 de 0.73 (só BioRED) → 0.85 (BioRED + TBGA + augmentation).

### Por que GWAS Catalog como fonte separada?

O GWAS Catalog [4] (Sollis et al. 2023) fornece associações com **odds ratios reais** — evidência estatística quantitativa de estudos com milhares de participantes (significância genômica p < 5×10⁻⁸). É a fonte mais confiável que existe. Estas associações são importadas diretamente sem passar por NER ou classificação ML.

### Por que HunFlair2 e não spaCy?

spaCy `en_ner_bc5cdr_md` extraía frases inteiras como nomes de doenças (56% dos dados inválidos). HunFlair2 [5] (Sänger et al. 2024) alcançou o melhor F1-score médio em avaliação cross-corpus para NER biomédico, com modelos para genes/proteínas, químicos, doenças, espécies e linhagens celulares. Produz spans corretos, tem confidence score por entidade, e reconhece múltiplos tipos em um passo.

### Por que duas fases (NER → Classify) e não pipeline simultâneo?

Separar permite: (1) batch_size maior na classificação (128 vs 32), (2) liberar VRAM do NER antes de classificar, (3) evitar fragmentação de VRAM que causava OOM. Com NER na GPU + classificação na GPU em fases separadas, não há conflito de memória.

### Por que NER + BERT RE e não NLI?

NLI classifica a **frase inteira** — se menciona 2 SNPs e 2 doenças, não sabe qual par está relacionado. BERT RE com entity markers (`@SNP@ ... #Disease#`) classifica **cada par** individualmente, seguindo a abordagem de Luo et al. [2] no BioRED. Mais preciso para abstracts que discutem múltiplas variantes.

---

## Rastreabilidade

Cada predição no `snp_preds` mantém o **PMID** do artigo original (`pmid INTEGER NOT NULL`).

- `GET /evidence/{pred_id}` — retorna predição + artigo original + SNP
- `GET /evidence/pmid/{pmid}` — verifica cadeia snps → snp_articles → articles → snp_preds
- `lib/traceability.py` — funções de auditoria programática

---

## Estrutura de Arquivos

```
vanda/
├── run_all.py                    # Script unificado do pipeline
├── database.sqlite               # Banco de produção (~450MB)
├── Dockerfile.pipeline           # Docker para rodar pipeline com GPU
├── main.py                       # Entry point FastAPI
│
├── lib/                          # Módulos compartilhados
│   ├── entrez.py                 # Cliente NCBI unificado (batch, rate limit)
│   ├── db.py                     # Helper de conexão SQLite
│   ├── ner.py                    # HunFlair2 NER (GPU/CPU auto)
│   ├── migrations.py             # Migrações de schema
│   ├── traceability.py           # Auditoria de PMID
│   └── integrations.py           # gnomAD, ClinVar, FooDB detalhado
│
├── app/                          # API FastAPI
│   ├── routers/
│   │   ├── search.py             # GET /search/
│   │   ├── snp.py                # GET /snp/{id}
│   │   ├── gene.py               # GET /gene/{id}
│   │   ├── variants.py           # GET /snps/food-analize/{food}
│   │   ├── evidence.py           # GET /evidence/{id}
│   │   ├── enrichment.py        # GET /enrich/* (gnomAD, ClinVar, FooDB)
│   │   ├── disease.py           # GET /disease/{name}
│   │   ├── info.py              # GET /info/* (MeSH descriptions)
│   │   └── suggest.py           # GET /suggest (autocomplete)
│   ├── models.py                 # Pydantic response models
│   ├── entrez/__init__.py        # Re-exporta de lib/entrez
│   ├── tokenizer/__init__.py     # NER wrapper para API
│   ├── summary/__init__.py       # Sumarização médica
│   └── utils/render_topics.py    # Agrupamento de tópicos
│
├── training/                     # Pipeline de treino
│   ├── biored_data.py            # Combina BioRED + TBGA + GWAS
│   ├── train.py                  # Fine-tuning PubMedBERT
│   ├── predict.py                # Inferência standalone
│   └── gwas_import.py            # Importação GWAS Catalog
│
├── download/
│   └── main.py                   # Pipeline de coleta NCBI/PubMed
│
├── pipeline/                     # Pipeline concorrente (alternativo)
│   ├── run.py                    # Orquestrador com stages
│   ├── stages.py                 # Download/NER/Classify/DBWriter stages
│   └── rate_limiter.py           # Rate limiter NCBI
│
└── docs/
    └── ARCHITECTURE.md           # Este arquivo
```

---

## Performance

### Tempos de execução (GTX 1060 6GB, 6K artigos)

| Etapa | Tempo |
|---|---|
| Migrações | ~5s |
| Datasets (BioRED+TBGA+GWAS) | ~2 min |
| Treino PubMedBERT (10 epochs) | ~4.5 horas |
| GWAS Import | ~1 min |
| Download NCBI (~261K SNPs) | ~1.5 horas |
| NER GPU (6K artigos → 345K pares) | ~45 min |
| Classificação GPU (345K pares, batch 128) | ~90 min |
| **Total (primeira vez)** | **~8-9 horas** |
| **Incremental (só artigos novos)** | **~1-2 horas** |

### Consumo de recursos

| Recurso | NER (Fase A) | Classify (Fase B) | Ambos |
|---|---|---|---|
| VRAM | ~1.0 GB | ~1.5 GB | N/A (fases separadas) |
| RAM | ~2 GB | ~3 GB | — |
| CPU | Mínimo | Tokenização | — |

---

## Frontend (Next.js)

Repositório separado: `vanda-f/`

### Stack
- Next.js 15 + React 19 + TypeScript
- Shadcn/ui (12+ componentes: Command, Dialog, Badge, Card, Tabs, Tooltip, Progress, etc.)
- Recharts (pie charts, bar charts)
- Tailwind CSS + animações
- i18n EN/PT-BR

### Páginas

| Rota | Descrição |
|---|---|
| `/` | Homepage: busca unificada, stats, cards top diseases/genes/foods, metodologia |
| `/snp/[id]` | Detalhe SNP: tabs Associations/Population/Foods/Articles, ClinVar, gnomAD |
| `/gene/[name]` | Detalhe gene: SNPs, artigos, compostos nutricionais, recomendações |
| `/food/[name]` | Análise alimento: descrição MeSH, DataTable interativa, charts |
| `/disease/[name]` | Análise doença: descrição MeSH, DataTable, genes, alimentos relacionados |
| `/about` | Equipe, metodologia, instituição |

### Funcionalidades do Frontend

- **Busca unificada** com autocomplete real do banco (`/suggest` API)
- **DataTable interativa**: filtro texto, filtro por efeito/fonte, ordenação, paginação, download CSV
- **i18n EN/PT-BR**: toggle no header, todos os labels traduzidos
- **Termos leigos**: Reliability (%), Protective/Risk, Clinical Study (GWAS), Literature Analysis (AI)
- **Rastreabilidade**: link PMID → PubMed em cada associação
- **Empty states**: componente reutilizável quando não há dados
- **Glossário interativo**: tooltip explicativo para termos técnicos
- **Gráfico de rede**: grafo canvas interativo com nós clicáveis (gene↔disease↔food)
- **Painel de recomendações**: alimentos relacionados, efeitos protetores, fatores de risco

### Equipe

- **Dr. Lucas Marques da Cunha** — Orientador (Ph.D. Bioinformática, UNIR/DACC)
- **Ricardo Alves da Silva** — Pesquisador (ricardcpu@gmail.com)
- **Thauan Silva** — Pesquisador (thauansilva243@gmail.com)

### Dados atuais (pós-limpeza)

| Métrica | Valor |
|---|---|
| SNPs catalogados | 261K |
| Predições limpas (pós-validação) | 11.3K |
| Artigos PubMed | 6K |
| Links food-gene (FooDB) | 3.3M |
| GWAS associations | 3.8K |
| IA associations | 8.8K |
| Overlap GWAS↔IA | 134 pares |
| Concordância | 50 pares (37%) |
| F1-score modelo | 0.8465 |

---

## Referências

[1] Gu, Y., Tinn, R., Cheng, H., Lucas, M., Usuyama, N., Liu, X., Naumann, T., Gao, J., & Poon, H. (2021). Domain-specific language model pretraining for biomedical natural language processing. *ACM Transactions on Computing for Healthcare*, 3(1), 1–23. https://doi.org/10.1145/3458754

[2] Luo, L., Lai, P.-T., Wei, C.-H., Arighi, C. N., & Lu, Z. (2022). BioRED: A rich biomedical relation extraction dataset. *Briefings in Bioinformatics*, 23(5), bbac282. https://doi.org/10.1093/bib/bbac282

[3] Marchesin, S., & Silvello, G. (2022). TBGA: A large-scale gene-disease association dataset for biomedical relation extraction. *BMC Bioinformatics*, 23, 111. https://doi.org/10.1186/s12859-022-04646-6

[4] Sollis, E., Mosaku, A., Abid, A., Buniello, A., Cerezo, M., Gil, L., ... & Harris, L. W. (2023). NHGRI-EBI GWAS Catalog: knowledgebase and deposition resource. *Nucleic Acids Research*, 51(D1), D977–D985. https://doi.org/10.1093/nar/gkac1010

[5] Sänger, M., Garda, S., Wang, X. D., Weber-Genzel, L., Droop, P., Fuchs, B., Akbik, A., & Leser, U. (2024). HunFlair2 in a cross-corpus evaluation of biomedical named entity recognition and normalization tools. *Bioinformatics*, 40(10), btae564. https://doi.org/10.1093/bioinformatics/btae564

[6] Karczewski, K. J., Francioli, L. C., Tiao, G., Cummings, B. B., Alföldi, J., Wang, Q., ... & MacArthur, D. G. (2020). The mutational constraint spectrum quantified from variation in 141,456 humans. *Nature*, 581, 434–443. https://doi.org/10.1038/s41586-020-2308-7

[7] FooDB — The Food Database. The Metabolomics Innovation Centre (TMIC). https://foodb.ca/

[8] Lee, J., Yoon, W., Kim, S., Kim, D., Kim, S., So, C. H., & Kang, J. (2020). BioBERT: a pre-trained biomedical language representation model for biomedical text mining. *Bioinformatics*, 36(4), 1234–1240. https://doi.org/10.1093/bioinformatics/btz682

[9] Lai, P.-T., Wei, C.-H., Luo, L., & Lu, Z. (2023). BioREx: Improving biomedical relation extraction by leveraging heterogeneous datasets. *Journal of Biomedical Informatics*, 146, 104487. https://doi.org/10.1016/j.jbi.2023.104487

[10] Sherry, S. T., Ward, M. H., Kholodov, M., Baker, J., Phan, L., Smigielski, E. M., & Sirotkin, K. (2001). dbSNP: the NCBI database of genetic variation. *Nucleic Acids Research*, 29(1), 308–311. https://doi.org/10.1093/nar/29.1.308

[11] Landrum, M. J., Lee, J. M., Benson, M., Brown, G. R., Chao, C., Chitipiralla, S., ... & Maglott, D. R. (2018). ClinVar: improving access to variant interpretations and supporting evidence. *Nucleic Acids Research*, 46(D1), D1062–D1067. https://doi.org/10.1093/nar/gkx1153

[12] Zhang, J., Yu, Y., Li, Y., Wang, Y., Yang, H., Li, M., & Zhang, L. (2022). A survey on programmatic weak supervision. *arXiv preprint arXiv:2202.05433*. https://doi.org/10.48550/arXiv.2202.05433
