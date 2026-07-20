# VANDA — Documentação Técnica

## O que é o VANDA?

O VANDA é uma plataforma de nutrigenética que extrai, classifica e disponibiliza relações entre **variantes genéticas (SNPs)**, **genes**, **doenças** e **alimentos** a partir de literatura científica do PubMed.

**Ponto-chave do projeto**: Automatizar a extração de conhecimento nutrigenético que hoje está disperso em milhares de artigos científicos, tornando-o acessível para profissionais de saúde e pesquisadores. A plataforma responde perguntas como: *"Quais variantes genéticas influenciam a resposta do organismo à manteiga?"* — conectando SNPs, genes, doenças e alimentos em uma interface consultável.

**Ideia central**: Pessoas diferentes respondem de forma diferente aos mesmos nutrientes por causa de suas variações genéticas (SNPs). O VANDA busca mapear essas relações automaticamente.

---

## Pipeline de Dados — Passo a Passo

### Etapa 1: Coleta de Dados (`download/main.py`)

**O que faz**: Busca todos os SNPs com artigos citados no PubMed e baixa os metadados dos artigos.

**Como funciona**:
1. Consulta o NCBI Entrez com o filtro `snp_pubmed_cited[Filter] OR snp_pubmed[Filter]`
2. Para cada SNP encontrado, busca o HGVS (nomenclatura de mutação) e o gene associado
3. Usa `Entrez.elink()` para ligar cada SNP aos seus artigos PubMed
4. Filtra artigos por termos MeSH de nutrigenética: Nutrients, Nutrigenomics, Nutrigenetics, Diet, Diets
5. Baixa título e abstract de cada artigo filtrado
6. Salva tudo no SQLite: tabelas `snps`, `articles`, `snp_articles`

**Saída**: `database.sqlite` com ~261K SNPs, ~100K artigos, ~463K relações SNP-artigo

**Dependências**: BioPython (Entrez API), requests

### Etapa 2: Extração de Entidades (NER) (`lib/ner.py`)

**O que faz**: Identifica menções a doenças, genes, químicos e SNPs nos abstracts.

**Como funciona**:
1. **HunFlair2** (modelo de NER biomédico baseado em Flair) identifica entidades:
   - `Disease` — ex: "Type 2 Diabetes", "Breast Cancer"
   - `Gene` — ex: "MTHFR", "CYP1A2"
   - `Chemical` — ex: "folate", "caffeine"
2. **Regex** complementar identifica SNPs: `rs1801133`, `c.677C>T`, `p.Ala222Val`
3. Cada entidade recebe um **score de confiança** do modelo

**Por que HunFlair2**: O modelo anterior (spaCy `en_ner_bc5cdr_md`) extraía frases inteiras como nomes de doenças — 56% dos dados estavam incorretos. HunFlair2 é estado da arte para NER biomédico e produz spans corretos.

### Etapa 3: Classificação de Relações (`training/train.py` + `training/predict.py`)

**O que faz**: Para cada par (SNP/Gene, Doença) encontrado no mesmo contexto, classifica a relação como **beneficial**, **harmful**, **neutral** ou **no_relation**.

**Como funciona**:
1. **Treino** (uma vez):
   - Baixa o dataset **BioRED** do NCBI (~600 abstracts anotados por especialistas)
   - Fine-tuna **PubMedBERT** (`microsoft/BiomedNLP-PubMedBERT`) no BioRED
   - Input usa **entity markers**: `"The @rs1801133@ variant reduced risk of #neural tube defects#"`
   - O modelo aprende a classificar a relação entre as entidades marcadas
   - Métrica: F1-macro na validação

2. **Inferência** (incremental):
   - Para cada artigo, segmenta em janelas de 3 frases
   - Extrai entidades com HunFlair2
   - Para cada par (Gene/SNP, Disease), cria input com entity markers
   - PubMedBERT classifica: beneficial, harmful, neutral, no_relation
   - Salva no `snp_preds` com **confidence score** (softmax probability)
   - Apenas processa artigos novos (pipeline incremental via `pipeline_state`)

**Mapeamento BioRED → VANDA**:
- `Positive_Correlation` (variante aumenta risco de doença) → **harmful**
- `Negative_Correlation` (variante diminui risco) → **beneficial**
- `Association` (associação sem direção clara) → **neutral**

### Etapa 4: Integração com Alimentos

**O que faz**: Conecta genes a alimentos usando a base FooDB.

**Como funciona**: A tabela `foods` (3.3M registros, pré-importada do FooDB) mapeia cada gene aos alimentos que contêm nutrientes metabolizados por esse gene. O JOIN com `snp_preds` via `gene_info` permite responder: *"Para este alimento, quais SNPs são benéficos/prejudiciais?"*

### Etapa 5: API (`app/routers/`)

**Endpoints**:
- `GET /search/?query=MTHFR` — Busca SNPs por gene/keyword
- `GET /snp/{snp_id}` — Detalhes de um SNP com tópicos de doença
- `GET /gene/{gene_id}` — Informações do gene com artigos agrupados
- `GET /snps/food-analize/{food_name}` — Análise de um alimento: genes, SNPs, direções
- `GET /evidence/{pred_id}` — Rastreabilidade: artigo original + SNP + confidence

---

## Banco de Dados

### Tabelas principais (`database.sqlite`)

| Tabela | Descrição | ~Registros |
|---|---|---|
| `snps` | SNP ID, HGVS, gene associado | 261K |
| `articles` | PMID, título, abstract do PubMed | 100K |
| `snp_articles` | Relação N:N entre SNPs e artigos | 463K |
| `foods` | Gene → alimento (FooDB) | 3.3M |
| `snp_preds` | Predições: SNP, doença, direção, confidence | 277K |
| `pipeline_state` | Estado do pipeline incremental | < 10 |

### Schema do `snp_preds`
```sql
CREATE TABLE snp_preds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pmid INTEGER NOT NULL,          -- rastreabilidade ao artigo original
    title TEXT,
    snp TEXT NOT NULL,              -- ex: RS1801133
    disease TEXT NOT NULL,          -- ex: Type 2 Diabetes
    direction TEXT NOT NULL,        -- beneficial, harmful, neutral
    confidence REAL NOT NULL,       -- 0.0 a 1.0 (probabilidade do modelo)
    model_version TEXT,             -- ex: pubmedbert-biored-v1
    created_at TIMESTAMP
);
```

---

## FAQ — Decisões Técnicas

### Por que não usar LLMs (ChatGPT, Claude) para classificação?

**Pontos fortes de LLMs**:
- Qualidade de classificação superior (~90-95% acurácia)
- Zero-shot, sem necessidade de dados de treino
- Flexibilidade para extrair qualquer tipo de relação

**Pontos fracos para este caso**:
- **Custo**: Processar ~100K artigos custaria $15-30+ por execução
- **Velocidade**: Muito mais lento que modelos locais
- **Dependência externa**: API pode mudar, ficar offline, ou mudar preços
- **Reprodutibilidade**: Resultados podem variar entre versões do modelo
- **Privacidade**: Dados enviados para servidores externos

**Decisão**: Usar modelos locais (PubMedBERT) para independência, reprodutibilidade e custo zero após treino.

### Por que PubMedBERT e não BioBERT?

**BioBERT v1.1 (2019)**:
- Pontos fortes: Pioneiro em BERT biomédico, amplamente citado
- Pontos fracos: Adaptado do BERT geral (pré-treino genérico + fine-tuning em PubMed), vocabulário não otimizado para biomedicina

**PubMedBERT (2020)**:
- Pontos fortes: Pré-treinado **do zero** em PubMed, vocabulário biomédico nativo, melhor performance em 6+ benchmarks biomédicos
- Pontos fracos: Nenhum significativo comparado ao BioBERT

**Decisão**: PubMedBERT é estritamente superior ao BioBERT para tarefas biomédicas. Mesma arquitetura, mesma velocidade, melhor performance.

### Por que BioRED e não weak labeling?

**Weak labeling (abordagem anterior)**:
- Pontos fortes: Gera dados de treino automaticamente, sem custo de anotação
- Pontos fracos: **~50% de acurácia** nas classificações (testado empiricamente). Termos como "risk" são ambíguos — "no risk" deveria ser beneficial mas triggers harmful. Resultado: modelo treinado em dados ruidosos replica os erros.

**BioRED dataset**:
- Pontos fortes: ~600 abstracts anotados por **especialistas do NCBI**. Relações entre Gene-Disease com tipos (Positive/Negative Correlation, Association). Gold standard reconhecido na comunidade.
- Pontos fracos: Menor volume (~600 docs vs ~100K). Porém, qualidade >>> quantidade para fine-tuning de modelos pré-treinados.

**Decisão**: Dados limpos de especialistas > muitos dados ruidosos. PubMedBERT já tem conhecimento biomédico do pré-treino; BioRED ensina a tarefa específica de classificação de relações.

### Por que HunFlair2 e não spaCy?

**spaCy en_ner_bc5cdr_md (abordagem anterior)**:
- Pontos fortes: Rápido, fácil de usar
- Pontos fracos: **Extraía frases inteiras como nomes de doenças**. Exemplo: `"Analysis Of The Current List Of Type 2 Diabetes"` em vez de `"Type 2 Diabetes"`. 56% dos dados no `snp_preds` tinham doenças inválidas.

**HunFlair2**:
- Pontos fortes: Estado da arte para NER biomédico. Reconhece Disease, Chemical, Gene/Protein, Species. Spans corretos. Confidence score por entidade.
- Pontos fracos: Mais pesado (~1.5GB vs ~200MB). Mais lento que spaCy.

**Decisão**: Qualidade do NER é fundamental — se as entidades extraídas são lixo, toda a classificação downstream é lixo. HunFlair2 resolve o problema na raiz.

### Por que NER + BERT RE e não NLI?

**NLI (Natural Language Inference)**:
- Pontos fortes: Zero-shot, sem fine-tuning, modelo pequeno (~300MB), roda em CPU
- Pontos fracos: Classifica o **texto inteiro**, não pares de entidades. Se uma frase menciona 2 SNPs e 2 doenças, NLI não sabe qual SNP se relaciona com qual doença.

**BERT Relation Extraction (BioRED)**:
- Pontos fortes: Classifica **cada par de entidades** individualmente com entity markers. Preciso em frases com múltiplas entidades. Mais rápido na inferência (~500 sent/s vs ~100 sent/s do NLI).
- Pontos fracos: Precisa de fine-tuning e GPU para treino.

**Decisão**: Abstracts científicos frequentemente discutem múltiplos SNPs e doenças. Entity-level RE é mais preciso que sentence-level classification.

### Por que não REBEL ou PL-Marker?

**REBEL**:
- Pontos fortes: End-to-end relation extraction via seq2seq
- Pontos fracos: Treinado em domínio genérico (Wikipedia). Modelo generativo = lento (~10 sent/s). Precisaria fine-tuning extensivo para biomedicina.

**PL-Marker**:
- Pontos fortes: Estado da arte em RE biomédico
- Pontos fracos: Setup complexo, dependências pesadas, não tem relações nutrigenéticas pré-treinadas.

**Decisão**: PubMedBERT + BioRED é o melhor custo-benefício — modelo estabelecido, dataset reconhecido, implementação simples.

---

## Rastreabilidade

Cada predição no `snp_preds` mantém o **PMID** do artigo original. Isso permite:

1. **Verificação**: O endpoint `/evidence/{pred_id}` retorna a predição + artigo original + SNP
2. **Auditoria**: `lib/traceability.py` verifica a cadeia `snps → snp_articles → articles → snp_preds`
3. **Transparência**: O usuário pode sempre voltar ao abstract original para validar a classificação

A rastreabilidade é **obrigatória** — nenhuma predição é salva sem PMID (`pmid INTEGER NOT NULL`).

---

## Como Rodar o Pipeline Completo

```bash
# 1. Coleta de dados (precisa de EMAIL no .env para NCBI)
cd download && python main.py

# 2. Migrar schema do banco
python -m lib.migrations --db database.sqlite --import-from download/snp_database.sqlite

# 3. Preparar dataset BioRED (uma vez)
cd training && python biored_data.py --output biored_processed.json

# 4. Treinar PubMedBERT (precisa GPU)
cd training && python train.py --data biored_processed.json --output ./model --epochs 5

# 5. Rodar inferência (incremental)
cd training && python predict.py --model ./model --db ../database.sqlite --min-confidence 0.7

# 6. Subir API
fastapi run
```

---

## Estrutura de Arquivos

```
vanda/
├── main.py                      # Entry point FastAPI
├── database.sqlite               # Banco de produção
├── lib/                          # Módulos compartilhados
│   ├── entrez.py                 # Cliente NCBI unificado
│   ├── db.py                     # Helper de conexão SQLite
│   ├── ner.py                    # HunFlair2 NER + regex SNP
│   ├── migrations.py             # Migrações de schema
│   └── traceability.py           # Auditoria de PMID
├── app/                          # API FastAPI
│   ├── routers/
│   │   ├── search.py             # GET /search/
│   │   ├── snp.py                # GET /snp/{id}
│   │   ├── gene.py               # GET /gene/{id}
│   │   ├── variants.py           # GET /snps/food-analize/{food}
│   │   └── evidence.py           # GET /evidence/{id}
│   ├── models.py                 # Pydantic response models
│   ├── tokenizer/__init__.py     # NER wrapper para API
│   ├── summary/__init__.py       # Sumarização médica
│   └── utils/render_topics.py    # Agrupamento de tópicos
├── download/
│   └── main.py                   # Pipeline de coleta NCBI/PubMed
├── training/
│   ├── biored_data.py            # Preparação dataset BioRED
│   ├── train.py                  # Fine-tuning PubMedBERT
│   └── predict.py                # Inferência + popular snp_preds
└── docs/
    └── ARCHITECTURE.md           # Este arquivo
```
