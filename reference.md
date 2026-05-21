# Azure AI Search — Presentation Reference

A consolidated reference for the Azure AI Search demo. Each section ties back
to a concrete artifact in this repo (`index/*.json`, `scripts/*.sql`, etc.) so
you can show, not just tell.

All citations link to Microsoft Learn. Stable REST API in examples is
`2026-04-01` unless noted.

---

## 1. What Azure AI Search Is

Azure AI Search is a **PaaS information-retrieval engine** for building
search, RAG, and agentic-retrieval experiences. It combines:

- **Lexical (BM25)** full-text search over inverted indexes
- **Vector** similarity search (HNSW / exhaustive KNN)
- **Hybrid** search that fuses both with Reciprocal Rank Fusion (RRF)
- **Semantic ranker** — an L2 ML reranker for top results
- **Indexer pipelines** that pull from Azure data sources and enrich with AI

Top-level objects you'll work with:

| Object | Purpose |
| --- | --- |
| **Index** | Schema + physical storage for your searchable documents |
| **Data source** | Connection to an external store (Blob, SQL, Cosmos, etc.) |
| **Indexer** | Job that copies + transforms data into an index |
| **Skillset** | Optional AI-enrichment pipeline attached to an indexer |
| **Knowledge base / source** | Agentic-retrieval orchestration objects |

> Ref: [What is Azure AI Search?](https://learn.microsoft.com/azure/search/search-what-is-azure-search)

---

## 2. Anatomy of an Index

### 2.1 Field types

The most useful types ([full list](https://learn.microsoft.com/rest/api/searchservice/supported-data-types)):

| Type | Notes |
| --- | --- |
| `Edm.String`, `Collection(Edm.String)` | Text. Collections can't be sortable. |
| `Edm.Int32`, `Edm.Int64`, `Edm.Double` | Numeric; filterable, sortable, facetable. |
| `Edm.Boolean` | Filter/facet/sort. |
| `Edm.DateTimeOffset` | Filter/facet/sort. |
| `Edm.GeographyPoint` | Geo, point-only with SRID 4326. |
| `Edm.ComplexType` | Nested objects. |
| `Collection(Edm.Single)` (+ vector variants) | Vector field. Searchable only via vector query, not filterable/facetable. |

### 2.2 Field attributes — the cheat sheet

| Attribute | Effect | Storage cost |
| --- | --- | --- |
| `key` | Exactly one per index. Must be `Edm.String`. | Required |
| `searchable` | Field participates in full-text or vector search. Strings are tokenized by the analyzer. | High |
| `filterable` | Allows `$filter=` expressions. **Strings aren't tokenized for filters** — comparisons are exact. | Medium |
| `sortable` | Allows `$orderby=`. Not allowed on `Collection(Edm.String)`. | Low–medium |
| `facetable` | Enables `facets=` (bucket counts). | Medium |
| `retrievable` | Returned in results / `$select`. Set `false` for fields you only use for filtering or scoring. | Free |

**Hidden gotcha:** `Edm.String` fields that are filterable/sortable/facetable
are treated as a single search term and capped at **32 KB per value**. If a
field can be larger than that (long bodies, free text), set those flags to
`false`.

> Ref: [Search indexes — schema](https://learn.microsoft.com/azure/search/search-what-is-an-index#schema-of-a-search-index)
> · [Create index — field definitions](https://learn.microsoft.com/azure/search/search-how-to-create-search-index#configure-field-definitions)

### 2.3 Facetable fields

Facetable fields power "filter sidebar" UIs — Search returns `value→count`
buckets scoped to the current result set:

```json
"@search.facets": {
  "tags":  [{"value":"grinder","count":42}, ...],
  "kind":  [{"value":"answer","count":118}, {"value":"question","count":47}]
}
```

Rules of thumb:

- Make **low-cardinality / categorical** fields facetable: `kind`, `tags`, `isAccepted`.
- For numeric/date fields, use **bucketing**: `facets=score,interval:10` or `facets=creationDate,values:2023-01-01|2024-01-01`.
- **Never** facet free-text or unique IDs — wastes storage, useless output.
- Typical pairing: facetable + filterable on the same field.

> Ref: [Faceted navigation](https://learn.microsoft.com/azure/search/search-faceted-navigation)

### 2.4 Suggesters

Suggesters power **type-ahead / autocomplete**. Defined at index level with
a list of source fields:

```json
"suggesters": [
  { "name": "sg", "searchMode": "analyzingInfixMatching",
    "sourceFields": ["title", "tags"] }
]
```

Each source field gets an additional verbatim-character index, so don't add
fields you won't use for suggestions.

> Ref: [index-add-suggesters](https://learn.microsoft.com/azure/search/index-add-suggesters)

### 2.5 Analyzers

Strings can be associated with an **analyzer** that handles tokenization
during indexing and query. Common choices:

- `en.microsoft` / `en.lucene` — language-aware tokenization, stemming, stopwords.
- `keyword` — treats the entire field as one token (good for IDs, codes).
- Custom analyzers built from tokenizers + token filters.

Use `searchAnalyzer` + `indexAnalyzer` separately when query- and
index-time behavior should differ.

> Ref: [Add language analyzers](https://learn.microsoft.com/azure/search/index-add-language-analyzers)
> · [Custom analyzers](https://learn.microsoft.com/azure/search/index-add-custom-analyzers)

---

## 3. Data Sources & Indexers

Indexers pull from a supported data source and write documents into an
index. The pipeline:

```
[ Data source ]  →  [ Indexer ]  →  [ Skillset (optional) ]  →  [ Index ]
```

### 3.1 Supported sources (subset)

- **Azure Blob Storage** — JSON, CSV, PDF, Office docs (cracking + OCR available via skillsets)
- **Azure SQL Database / Managed Instance**
- **Cosmos DB** (NoSQL, MongoDB, Gremlin)
- **Azure Table Storage**, **Azure Files**, **ADLS Gen2**, **OneLake**

> Ref: [Indexer overview](https://learn.microsoft.com/azure/search/search-indexer-overview)

### 3.2 Blob path — the JSON variant we use

Used by the existing `coffee-posts-flat` index. The flattened JSON (one
question OR answer per row) lives in blob storage; the indexer reads each
row as a document, applies `parsingMode = jsonArray`, and writes to the
index. Use this path when source data is already in document form.

### 3.3 Azure SQL path

Configurable from a **table or a view**. A view is what the demo uses — it
lets you reshape relational data without ETL.

**Requirements** (Stack-Exchange-coffee demo highlights):

- Primary key must be single-valued. On a table, also non-clustered.
- For a view, you **must** use a `HighWaterMarkChangeDetectionPolicy`
  (SQL integrated change tracking only works on tables).
- The HWM column should ideally be `rowversion`; we used a `DATETIME2`
  (`LastActivityDateHWM`) for simplicity.

```json
// index/coffee-posts-sql-datasource.json
{
  "name": "coffee-posts-sql-ds",
  "type": "azuresql",
  "credentials": { "connectionString": "<ADO.NET conn string>" },
  "container": { "name": "vw_CoffeePostsFlat" },
  "dataChangeDetectionPolicy": {
    "@odata.type": "#Microsoft.Azure.Search.HighWaterMarkChangeDetectionPolicy",
    "highWaterMarkColumnName": "LastActivityDateHWM"
  }
}
```

#### High-water-mark policy — how it works

On every run the indexer issues:

```sql
WHERE [HWM column] > [last seen value]
ORDER BY [HWM column]
```

The `[last seen value]` is the indexer's internal cursor (you don't see
it in the API). For correctness:

1. Every insert/update must change the column.
2. The column must monotonically increase.
3. There must be an index on the column or the query may time out.

Use the indexer parameter `convertHighWaterMarkToRowVersion: true` when
the column is `rowversion` — it subtracts 1 from the value before each
query so views with one-to-many joins (duplicate rowversion values)
don't lose rows.

> Ref: [Index data from Azure SQL — change detection](https://learn.microsoft.com/azure/search/search-how-to-index-sql-database#indexing-new-changed-and-deleted-rows)

#### SQL → Edm type mapping (relevant rows)

| SQL | Edm |
| --- | --- |
| `bit` | `Edm.Boolean`, `Edm.String` |
| `int`, `smallint`, `tinyint` | `Edm.Int32`, `Edm.Int64`, `Edm.String` |
| `decimal`, `money` | `Edm.String` (decimal → double loses precision) |
| `nvarchar` containing a JSON array (`["a","b"]`) | `Collection(Edm.String)` |
| `datetime2`, `datetimeoffset` | `Edm.DateTimeOffset` |
| `rowversion` | Not stored; HWM only |
| `time`, `binary`, `xml`, `geometry` | Not supported |

Numeric SQL IDs need to become strings when the index uses `Edm.String`
for the key — the demo's `scripts/alter_view_for_indexer.sql` does this
with `CAST(p.Id AS NVARCHAR(20))`.

> Ref: [SQL data type mapping](https://learn.microsoft.com/azure/search/search-how-to-index-sql-database#mapping-data-types)

### 3.4 Field mappings vs output field mappings

- **`fieldMappings`** — map *source columns* to *index fields*. Used when
  names differ, types need light conversion, or you split one source field
  into many (e.g. `jsonArrayToStringCollection`, `base64Encode`).
- **`outputFieldMappings`** — map *enriched values from the skillset*
  (`/document/...` paths) to *index fields*.

```json
"fieldMappings": [
  { "sourceFieldName": "tags", "targetFieldName": "tags",
    "mappingFunction": { "name": "jsonArrayToStringCollection" } }
],
"outputFieldMappings": [
  { "sourceFieldName": "/document/chunkVector", "targetFieldName": "chunkVector" }
]
```

Built-in mapping functions include `base64Encode/Decode`,
`jsonArrayToStringCollection`, `urlEncode/Decode`,
`extractTokenAtPosition`, and `fixedLengthEncoding`.

> Ref: [Field mappings](https://learn.microsoft.com/azure/search/search-indexer-field-mappings)

### 3.5 Scheduling and on-demand runs

- Schedule with `"schedule": { "interval": "PT1H" }` (ISO 8601).
- Manual run: `POST /indexers/{name}/run`.
- Force re-process every doc: `POST /indexers/{name}/reset` then run.
- A successful run reporting **0/0 documents** means the change-detection
  policy found nothing new — that's expected behavior, not a failure.

> Ref: [Create an indexer](https://learn.microsoft.com/azure/search/search-how-to-create-indexers)
> · [Schedule indexers](https://learn.microsoft.com/azure/search/search-howto-schedule-indexers)

---

## 4. Skillsets (AI Enrichment)

A **skillset** is an indexer-time pipeline of *skills* that enrich each
document. Built-in skills include OCR, key-phrase extraction, entity
recognition, language detection, PII detection, image analysis, text
splitting (chunking), document layout, and **embedding skills**. You can
also bring custom skills via Web API or AML endpoints.

Output goes into the enriched document tree (`/document/...`) and is
landed in the index via `outputFieldMappings`.

### 4.1 `AzureOpenAIEmbeddingSkill`

Generates vectors at indexing time using your Azure OpenAI embedding
deployment.

```json
{
  "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
  "context": "/document",
  "resourceUri": "https://<aoai>.openai.azure.com",
  "deploymentId": "text-embedding-3-small",
  "modelName": "text-embedding-3-small",
  "dimensions": 1536,
  "inputs":  [ { "name": "text",      "source": "/document/chunk" } ],
  "outputs": [ { "name": "embedding", "targetName": "chunkVector" } ]
}
```

Supported models: `text-embedding-ada-002`, `text-embedding-3-small`,
`text-embedding-3-large`. Input is capped at **8,000 tokens** — chunk
longer content first using `SplitSkill` or `DocumentLayoutSkill`.

Auth options: API key (shown above), or remove `apiKey` and grant the
search service's managed identity the
**Cognitive Services OpenAI User** role on the AOAI resource.

> Ref: [Azure OpenAI Embedding skill](https://learn.microsoft.com/azure/search/cognitive-search-skill-azure-openai-embedding)

### 4.2 Integrated vectorization

Two related but distinct features:

- **Index-time** (skill): the embedding skill above turns text into
  vectors before they land in the index.
- **Query-time** (vectorizer): a `vectorizer` declared in
  `vectorSearch.vectorizers` lets callers send *plain text* in queries —
  Search vectorizes it server-side using the same model.

Both should reference the **same embedding model** so query and document
vectors live in the same space.

> Ref: [Integrated vectorization concepts](https://learn.microsoft.com/azure/search/vector-search-integrated-vectorization)
> · [Configure a vectorizer](https://learn.microsoft.com/azure/search/vector-search-how-to-configure-vectorizer)

### 4.3 Chunking strategies

- `SplitSkill` — split by sentences or by character count with overlap.
- `DocumentLayoutSkill` — splits along paragraph / layout boundaries.
- `AzureContentUnderstandingSkill` — richer parsing for complex docs.
- Indexer's `parsingMode` options (`text`, `delimitedText`, `json`,
  `jsonArray`, `jsonLines`) handle ingest-time splitting.

> Ref: [Chunk large documents](https://learn.microsoft.com/azure/search/vector-search-how-to-chunk-documents)

---

## 5. Vector Search

### 5.1 Vector field essentials

```json
{ "name": "chunkVector",
  "type": "Collection(Edm.Single)",
  "searchable": true,
  "retrievable": false,
  "dimensions": 1536,
  "vectorSearchProfile": "default-profile" }
```

- Must be `searchable`.
- **Can't** be filterable, facetable, sortable, or have analyzers.
- `dimensions` must match the embedding model exactly.
- Pair with a `vectorSearchProfile`, which links an **algorithm** and an
  optional **vectorizer / compression**.

### 5.2 Algorithms

| Algorithm | When to use |
| --- | --- |
| **HNSW** (Hierarchical Navigable Small World) | Default. Fast approximate kNN, good recall. |
| **Exhaustive KNN** | Brute force — slower but guaranteed-correct, good for benchmarking or small data. |

HNSW knobs:

| Parameter | Default | Range | Effect |
| --- | --- | --- | --- |
| `m` | 4 | 4–10 | Bi-directional links per node. Higher = better recall, more memory. |
| `efConstruction` | 400 | 100–1000 | Candidate list during indexing. Higher = denser graph, slower build. |
| `efSearch` | 500 | 100–1000 | Candidate list during query. Higher = better recall, slower query. |
| `metric` | `cosine` | `cosine`, `dotProduct`, `euclidean`, `hamming` | Pick to match your embedding model — `cosine` for Azure OpenAI. |

> Ref: [Relevance in vector search (HNSW)](https://learn.microsoft.com/azure/search/vector-search-ranking)

### 5.3 Vector profiles

A profile is the indirection layer that ties algorithm + vectorizer +
compression to a vector field. One profile per vector field, but you can
declare many in an index:

```json
"vectorSearch": {
  "algorithms":  [ { "name": "hnsw-default", "kind": "hnsw", "hnswParameters": {...} } ],
  "profiles":    [ { "name": "default-profile",
                     "algorithm": "hnsw-default",
                     "vectorizer": "aoai-vectorizer" } ],
  "vectorizers": [ { "name": "aoai-vectorizer", "kind": "azureOpenAI",
                     "azureOpenAIParameters": {...} } ]
}
```

### 5.4 Querying vectors

Send a vector query with `kind = "text"` to use the vectorizer, or
`kind = "vector"` with a precomputed embedding:

```json
{
  "vectorQueries": [
    { "kind": "text", "text": "how do I store whole bean coffee?",
      "fields": "chunkVector", "k": 10 }
  ]
}
```

`exhaustive: true` bypasses HNSW and brute-forces — useful for
accuracy comparisons during demos.

> Ref: [Vector search overview](https://learn.microsoft.com/azure/search/vector-search-overview)

---

## 6. Hybrid Search

A **hybrid query** is a single request with both `search` (text) and
`vectorQueries` (vector). The engine runs them in parallel and fuses
results with **Reciprocal Rank Fusion (RRF)**.

```json
{
  "search": "storing whole bean coffee",
  "vectorQueries": [
    { "kind": "text", "text": "storing whole bean coffee",
      "fields": "chunkVector", "k": 50 }
  ],
  "top": 10
}
```

### 6.1 RRF in 30 seconds

For each document `d`, summed across the participating queries `q`:

```
score(d) = Σ_q  1 / (k + rank_q(d))
```

with constant `k = 60` (Search's choice). Properties:

- Result is **scale-invariant** — works even though BM25 and cosine
  scores have totally different magnitudes.
- Adding more queries raises the achievable upper bound on score.
- RRF scores look small (often `< 0.1`) — that's normal; don't compare
  them to BM25 numbers.

### 6.2 Why hybrid beats either alone

- Vector wins on semantic similarity, paraphrasing, conceptual queries.
- BM25 wins on exact tokens — product codes, names, jargon, rare words.
- Microsoft's published benchmarks show hybrid + semantic ranker
  consistently top.

### 6.3 Best practice with semantic ranker

When using semantic ranker on hybrid results, set `k` + `maxTextRecallSize`
to sum to ≥ 50, then trim with `top`. The reranker needs a reasonably
deep candidate pool to do its job.

> Ref: [Hybrid search overview](https://learn.microsoft.com/azure/search/hybrid-search-overview)
> · [RRF scoring](https://learn.microsoft.com/azure/search/hybrid-search-ranking)

---

## 7. Semantic Ranker (L2)

The semantic ranker is a Microsoft-hosted ML model that **rescores the
top results** of an L1 (BM25 / vector / RRF) query for relevance to the
user's intent. It also produces:

- **Captions** — extractive highlights of the most relevant span.
- **Semantic answers** — direct-answer snippets when the query is
  question-shaped.

### 7.1 Configuration

```json
"semantic": {
  "configurations": [
    {
      "name": "default-semantic",
      "prioritizedFields": {
        "titleField":               { "fieldName": "title" },
        "prioritizedContentFields": [ { "fieldName": "chunk" } ],
        "prioritizedKeywordsFields":[ { "fieldName": "tags" } ]
      }
    }
  ]
}
```

The reranker uses just these prioritized fields as input, so pick the
ones with **semantically rich** content.

### 7.2 Activating it on a query

```json
{
  "search": "espresso temperature",
  "queryType": "semantic",
  "semanticConfiguration": "default-semantic",
  "captions": "extractive",
  "answers":  "extractive"
}
```

Response surface:

| Score | Range | Meaning |
| --- | --- | --- |
| `@search.score` | depends on L1 algorithm | BM25 / HNSW / RRF |
| `@search.rerankerScore` | 0.00–4.00 | Semantic relevance |
| `@search.rerankerBoostedScore` | unbounded | Scoring profile applied **after** semantic reranking |

### 7.3 Pricing/region caveats

Semantic ranker is **billed per request** and only available in supported
regions. It's also a hard requirement for **agentic retrieval**.

> Ref: [Semantic ranker](https://learn.microsoft.com/azure/search/semantic-search-overview)
> · [Region support](https://learn.microsoft.com/azure/search/search-region-support)

---

## 8. Scoring Profiles

Custom boosting on top of L1 scoring. Two kinds of inputs:

1. **Weighted text fields** — boost matches in `title` more than `body`.
2. **Functions** — `magnitude`, `freshness`, `distance`, `tag`.

```json
"scoringProfiles": [{
  "name": "qa-relevance",
  "text": { "weights": { "title": 5, "body": 1 } },
  "functions": [
    { "type": "magnitude", "fieldName": "score",       "boost": 3,
      "interpolation": "logarithmic",
      "magnitude": { "boostingRangeStart": 0, "boostingRangeEnd": 100,
                     "constantBoostBeyondRange": true } },
    { "type": "freshness", "fieldName": "creationDate", "boost": 1.2,
      "interpolation": "quadratic",
      "freshness": { "boostingDuration": "P1095D" } }
  ],
  "functionAggregation": "sum"
}]
```

### 8.1 Interactions with vector / hybrid / semantic

- **Pure text**: scoring profile reweights BM25 top 1000, top 50 returned.
- **Pure vector**: applied to nonvector fields in the *k* matched docs.
- **Hybrid**: applied on text side **before RRF**, then again after fusion ("final document boosting adjustment").
- **Semantic ranker**: with `rankingOrder = "boostedRerankerScore"`, the profile is also applied **after** semantic reranking → `@search.rerankerBoostedScore`.

Use `tag` functions to apply per-user / per-tenant boosting from a
query-time parameter:

```json
{ "type": "tag", "fieldName": "isAccepted", "boost": 2,
  "tag": { "tagsParameter": "acceptedTag" } }
```

Then at query: `"scoringParameters": ["acceptedTag-true"]`.

> Ref: [Scoring profiles](https://learn.microsoft.com/azure/search/index-add-scoring-profiles)
> · [Scoring profiles + semantic ranker](https://learn.microsoft.com/azure/search/semantic-how-to-enable-scoring-profiles)

---

## 9. Relevance Levels — Putting It All Together

Microsoft's mental model for the scoring stack:

| Level | What happens | Score field |
| --- | --- | --- |
| **L1** | BM25 (text) or HNSW/KNN (vector). | `@search.score` |
| **Fused L1** | RRF merges multiple L1 results (hybrid or multi-vector). | `@search.score` (RRF range) |
| **L2** | Semantic ranker rescores top results. | `@search.rerankerScore` |
| **L3** | *Iterative search* used by agentic retrieval (`retrievalReasoningEffort: medium`). | n/a |

Scoring-profile boosts can sit at L1 (always) and after L2
(`rankingOrder: boostedRerankerScore`).

> Ref: [Relevance overview](https://learn.microsoft.com/azure/search/search-relevance-overview)

---

## 10. Agentic Retrieval

A **multi-query, multi-source retrieval pipeline** for chat/agent apps.

### 10.1 Pieces

| Component | Role |
| --- | --- |
| **Knowledge source** | Wraps a search index (or remote source) with retrieval-specific config. |
| **Knowledge base** | Orchestrator. Holds reference to source(s), the planning LLM, parameters. |
| **Planning LLM** | Decomposes the user's question (+ chat history) into focused subqueries. Currently `gpt-4o`, `gpt-4.1`, `gpt-5` series. |
| **Search service** | Runs subqueries in parallel, semantically reranks, merges. |

### 10.2 Workflow

1. App calls `knowledgeBase.retrieve(query, chatHistory)`.
2. LLM analyzes context → emits N subqueries (keyword / vector / hybrid).
3. Subqueries run in parallel against the knowledge source(s).
4. Each subquery's top results are **semantically reranked**.
5. A three-part response is returned:
   - **Grounding data** (extractive content or synthesized answer)
   - **References** (citations with source doc IDs)
   - **Activity plan** (query steps for transparency / debugging)

### 10.3 Two output modes

- `extractive` — verbatim content; the agent's downstream LLM decides what to do with it.
- `synthesis` — Search calls the LLM to compose a natural-language answer.

### 10.4 Reasoning effort

- `minimal` — no LLM planning, single subquery (cheap, fast).
- `low` / `medium` / `high` — progressively more decomposition and, at
  `medium`+, *iterative search* (L3 — re-issuing queries based on partial
  results).

### 10.5 Hard requirements

- The index **must** have a default semantic configuration.
- Vector fields are auto-used if they're `searchable` and assigned a
  vectorizer.
- Semantic ranker is required (premium feature).
- Generally available in REST `2026-04-01`; some features remain preview.

> Ref: [Agentic retrieval overview](https://learn.microsoft.com/azure/search/agentic-retrieval-overview)
> · [Build an end-to-end agentic pipeline](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-create-pipeline)

---

## 11. Security & Operations

### 11.1 Auth

- **API keys** (admin / query) — simple but rotate manually.
- **RBAC** — Search Service Contributor / Search Index Data Contributor / Search Index Data Reader. Disable keys for full RBAC mode.
- **Managed identity** on the search service — preferred for indexer-to-source and skill-to-AOAI auth. No connection-string secrets in data sources.

### 11.2 Networking

- **Private endpoints** on the search service.
- **Shared private link** for indexers + skills to reach private resources (SQL, Storage, AOAI).
- IP firewall on the search service for public-network deployments.

### 11.3 Limits to watch

| Limit | Notes |
| --- | --- |
| Indexer run time | Bounded; long blob/SQL pulls may hit ceiling on lower tiers. |
| Vector dimensions per field | Up to 3072 (model-dependent). |
| Indexes / fields per service | Tier-dependent; see service limits. |
| Embedding skill input | 8,000 tokens per call. |
| Scoring profiles per index | 100. |

> Ref: [Service limits](https://learn.microsoft.com/azure/search/search-limits-quotas-capacity)

### 11.4 Pricing tiers — what they gate

- **Free / Basic** — dev/test only; no semantic ranker.
- **S1 / S2 / S3** — semantic ranker available, more storage, replicas.
- **Storage-optimized (L1/L2)** — large indexes, fewer queries/sec.
- Semantic ranker billed per 1000 requests on top of base tier.

---

## 12. This Repo, Mapped to the Above

| File | Section |
| --- | --- |
| `posts_flat.json`, `scripts/flatten_posts.py` | §3.2 Blob path |
| `scripts/load_sql.py` | §3.3 Loading the SQL tables |
| `scripts/create_view.sql`, `scripts/alter_view_for_indexer.sql` | §3.3 View shape + HWM |
| `index/coffee-posts-flat-index.json` | §2 Index, §5 Vector, §7 Semantic |
| `index/coffee-posts-sql-index.json` | Same shape, tied to SQL source |
| `index/coffee-posts-sql-datasource.json` | §3.3 Azure SQL data source |
| `index/coffee-posts-sql-indexer.json` | §3.4 Field/output mappings |
| `index/coffee-posts-sql-skillset.json` | §4.1 AOAI embedding skill |

---

## 13. Demo Script — Suggested Flow

1. **Show source data.**
   `SELECT TOP 3 * FROM dbo.vw_CoffeePostsFlat;` — one row per Q or A.
2. **Run the SQL indexer** in the portal; watch tracking state advance.
3. **Run three queries** on the same prompt ("storing whole bean coffee"):
   1. `search=...` only → BM25
   2. `vectorQueries=[{kind:text,...}]` only → vector
   3. Both → hybrid; then add `queryType=semantic` for L2.
   Show the score fields change shape.
4. **Touch a row** in SQL (`UPDATE Posts SET LastActivityDate=GETUTCDATE() WHERE Id = X`).
5. **Re-run indexer** → it processes only that row. HWM working.
6. **(Optional)** Create a knowledge base over the index and ask a
   complex multi-part question to demonstrate agentic retrieval.

---

## 14. Further Reading

- [Azure AI Search — what's new](https://learn.microsoft.com/azure/search/whats-new)
- [REST API reference (2026-04-01)](https://learn.microsoft.com/rest/api/searchservice/)
- [Samples — `Azure-Samples/azure-search-vector-samples`](https://github.com/Azure/azure-search-vector-samples)
- [Samples — `Azure-Samples/azure-search-python-samples`](https://github.com/Azure-Samples/azure-search-python-samples)
- [Agentic retrieval Python notebook](https://github.com/Azure-Samples/azure-search-python-samples/tree/main/agentic-retrieval-pipeline-example)
