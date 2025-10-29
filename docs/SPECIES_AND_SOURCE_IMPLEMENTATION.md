# Species and Source Metadata Implementation Guide

## Overview

This document describes the implementation of species tracking and source provenance features for the BioGraph Knowledge Graph Generation Pipeline.

## What Was Implemented

### 1. Species Tracking
- **Purpose**: Accurately track which species (human, mouse, rat, etc.) findings apply to
- **Importance**: Critical for RAG applications to prevent false claims about human health based on animal studies

### 2. Source Provenance
- **Purpose**: Track which documents/papers contributed each piece of knowledge
- **Importance**: Enables citation, transparency, and multi-source knowledge aggregation

---

## Architecture Changes

### Core Concepts

#### **Species-Specific vs Universal Entities**

**Species-Specific** (species is part of node identity):
- `Gene`: Human TP53 vs Mouse Tp53 are different entities
- `Protein`: Different sequences across species
- `Anatomy`: Human liver vs mouse liver
- `Cell_Type`: Species-specific cell types

**Universal Concepts** (species NOT part of node identity):
- `Drug`: Aspirin is the same molecule regardless of species
- `Disease`: Disease concepts are universal abstractions
- `Treatment`, `Symptom`, `Biological_Process`: Process/concept abstractions

#### **Relationship Species Context**

ALL relationships include:
- `species`: Which species this observation applies to
- `species_confidence`: How certain we are
  - `"explicit"`: Directly stated in text chunk
  - `"inherited"`: Using document-level default
  - `"speculative"`: Hypothetical cross-species application
  - `"unknown"`: Cannot determine

---

## Implementation Details

### 1. Document Context Extraction

**Location**: `utils.py` - `extract_document_context()`

**What it does**:
- Reads first 75 lines of document (title, abstract, methods)
- Extracts via LLM in single call:
  - Title, authors, journal, year, DOI
  - Primary species studied
  - Study type (clinical trial, animal study, etc.)
- Returns complete metadata dictionary

**Example**:
```python
document_context = extract_document_context(
    file_path="data_corpus/PMC8675309.txt",
    source_id="PMC8675309",
    llm=llm
)
# Returns:
# {
#     'source_id': 'PMC8675309',
#     'title': 'Effects of Aspirin on...',
#     'journal': 'Nature Medicine',
#     'publication_year': '2023',
#     'primary_species': 'Mus musculus',
#     'species_confidence': 'high',
#     'study_type': 'animal study',
#     ...
# }
```

### 2. Species Logic Application

**Location**: `utils.py` - `apply_species_logic_to_node()`, `apply_species_logic_to_relationship()`

**Node Logic**:
```python
# For Gene (species-specific):
{
    "entity_name": "TP53",
    "entity_type": "Gene",
    "species": "Homo sapiens",
    "ontology_id": "BIOGRAPH:GENE:abc123_Homo_sapiens"  # Species in ID!
}

# For Drug (universal):
{
    "entity_name": "Aspirin",
    "entity_type": "Drug",
    # No species field
    "ontology_id": "BIOGRAPH:DRUG:xyz789"  # No species in ID
}
```

**Relationship Logic**:
```python
{
    "source": "Aspirin",
    "target": "Inflammation",
    "relation_type": "TREATS",
    "species": "Mus musculus",  # Always present
    "species_confidence": "inherited",  # Always present
    "source_id_ref": "PMC8675309"  # Reference to Source node
}
```

### 3. Neo4j Schema Updates

**Source Nodes** (new):
```cypher
(:Source {
    source_id: "PMC8675309",
    source_type: "research_article",
    source_platform: "PubMed Central",
    title: "Effects of Aspirin...",
    journal: "Nature Medicine",
    publication_year: "2023",
    primary_species: "Mus musculus",
    species_confidence: "high",
    study_type: "animal study",
    processing_date: "2025-10-29T..."
})
```

**Entity Nodes** (updated):
```cypher
// Universal entity (no species)
(:Drug {
    ontology_id: "BIOGRAPH:DRUG:aspirin",
    standard_name: "Aspirin",
    synonyms: [...],
    description: "...",
    embedding: [...]
})

// Species-specific entity
(:Gene {
    ontology_id: "BIOGRAPH:GENE:TP53_Homo_sapiens",
    standard_name: "TP53",
    species: "Homo sapiens",
    species_confidence: "inherited",
    synonyms: [...],
    description: "...",
    embedding: [...]
})
```

**EXTRACTED_FROM Relationships** (new):
```cypher
// Entity linked to Source
(entity)-[:EXTRACTED_FROM {
    extraction_date: datetime()
}]->(source:Source)
```

**Entity Relationships** (updated):
```cypher
(drug)-[r:TREATS {
    evidence_text: "...",
    species: "Mus musculus",
    species_confidence: "inherited",
    source_id: "PMC8675309"
}]->(disease)
```

### 4. Pipeline Flow

**Updated Process**:

```
1. Load Document
   ↓
2. Extract Document Context (first 75 lines)
   ├─ Bibliographic metadata
   ├─ Primary species
   └─ Study type
   ↓
3. Create Source Node in Neo4j
   ↓
4. Load Remaining Document (skip first 75 lines)
   ↓
5. Chunk Document
   ↓
6. FOR EACH CHUNK:
   ├─ Extract entities/relationships (LLM gets document context in prompt)
   ├─ Apply species logic to nodes
   ├─ Apply species logic to relationships
   ├─ Standardize with AWS Comprehend Medical
   ├─ Lookup synonyms from UMLS
   ├─ Generate embeddings
   └─ Add source_id to all nodes/relationships
   ↓
7. Load Batch to Neo4j
   ├─ Create/merge entity nodes
   ├─ Create EXTRACTED_FROM relationships to Source
   └─ Create entity relationships with species metadata
```

---

## Usage Examples

### Running the Pipeline

**Process single document (default behavior)**:
```bash
python run_pipeline.py
# Uses SOURCE_DOCUMENT_PATH from utils.py
```

**Process specific document**:
```bash
python run_pipeline.py --single-document path/to/document.txt
```

**Test mode (first 10 chunks)**:
```bash
python run_pipeline.py --test-mode
```

**Full run**:
```bash
python run_pipeline.py --full-run
```

### Querying the Knowledge Graph

#### Example 1: Find Human-Specific Effects of Aspirin
```cypher
MATCH (aspirin:Drug {standard_name: "Aspirin"})-[r]->(effect)
WHERE r.species = "Homo sapiens"
RETURN 
    effect.standard_name AS effect,
    r.relation_type AS relationship,
    r.species_confidence AS confidence,
    r.source_id AS source
```

#### Example 2: Compare Mouse vs Human Findings
```cypher
MATCH (drug:Drug {standard_name: "Aspirin"})-[r]->(effect)
WHERE r.species IN ["Homo sapiens", "Mus musculus"]
RETURN 
    r.species AS species,
    r.relation_type AS relationship,
    collect(effect.standard_name) AS effects
ORDER BY r.species
```

#### Example 3: Get All Sources for an Entity
```cypher
MATCH (entity {standard_name: "Aspirin"})-[:EXTRACTED_FROM]->(s:Source)
RETURN 
    s.source_id,
    s.title,
    s.journal,
    s.publication_year,
    s.primary_species
```

#### Example 4: Find Cross-Species Gene Studies
```cypher
MATCH (g:Gene)
WHERE g.species IS NOT NULL
WITH g.standard_name AS gene_name, collect(DISTINCT g.species) AS species_list
WHERE size(species_list) > 1
RETURN gene_name, species_list
ORDER BY size(species_list) DESC
```

#### Example 5: RAG Context Retrieval
```cypher
// For a user query about "aspirin side effects"
MATCH (aspirin:Drug {standard_name: "Aspirin"})-[r:HAS_SIDE_EFFECT]->(side_effect)
MATCH (s:Source {source_id: r.source_id})
RETURN {
    claim: aspirin.standard_name + " causes " + side_effect.standard_name,
    species: r.species,
    species_confidence: r.species_confidence,
    evidence: r.evidence_text,
    source_title: s.title,
    journal: s.journal,
    year: s.publication_year,
    study_type: s.study_type
} AS context
ORDER BY 
    CASE r.species 
        WHEN 'Homo sapiens' THEN 1  // Prioritize human studies
        ELSE 2 
    END,
    s.publication_year DESC  // Then by recency
```

---

## Key Files Modified

### `utils.py`
**New Constants**:
- `SPECIES_SPECIFIC_NODE_TYPES = ['Gene', 'Protein', 'Anatomy', 'Cell_Type']`
- `DOCUMENT_CONTEXT_EXTRACTION_PROMPT`

**New Functions**:
- `extract_document_context()`: Extract metadata + species from document header
- `apply_species_logic_to_node()`: Apply species handling to nodes
- `apply_species_logic_to_relationship()`: Apply species handling to relationships
- `create_source_node()`: Create Source node in Neo4j

**Updated Functions**:
- `EXTRACTION_PROMPT_TEMPLATE`: Added document context and species handling sections
- `process_text_chunk()`: Added `document_context` parameter, applies species logic
- `load_nodes_to_neo4j()`: Handles species fields, creates EXTRACTED_FROM relationships
- `load_relationships_to_neo4j()`: Includes species and source_id in relationships

### `run_pipeline.py`
**New Imports**:
- `extract_document_context`, `create_source_node`

**New Functions**:
- `get_document_list()`: Scan directory for documents
- `generate_source_id()`: Generate unique source IDs
- `load_document_skip_header()`: Load document skipping header

**New CLI Arguments**:
- `--single-document PATH`: Process specific document
- `--data-directory PATH`: Directory for multi-document processing (prepared for future)

**Updated Workflow**:
- Extract document context before processing chunks
- Create Source node in Neo4j
- Pass `document_context` to `process_text_chunk()`

---

## Testing Checklist

- [ ] **Single document processing**: Run with default document
- [ ] **Species extraction**: Verify species detected from abstract/methods
- [ ] **Source node creation**: Check Neo4j for Source nodes
- [ ] **EXTRACTED_FROM relationships**: Verify entities link to sources
- [ ] **Species-specific nodes**: Check Gene/Protein nodes have species in ontology_id
- [ ] **Universal nodes**: Check Drug/Disease nodes don't have species field
- [ ] **Relationship species**: Verify all relationships have species and species_confidence
- [ ] **Query verification**: Test sample Cypher queries above
- [ ] **Multi-species handling**: Test document mentioning multiple species
- [ ] **Checkpoint recovery**: Verify pipeline can resume mid-document

---

## Future Enhancements

### Phase 2: Full Multi-Document Support
- Update checkpoint schema to track document-level progress
- Add `--resume-from-document` argument
- Implement `completed_documents` tracking
- Add document-level progress bar

### Phase 3: Additional Features
- Cross-species relationship analysis
- Species-specific evidence scoring
- Temporal versioning (track knowledge evolution over time)
- Negation handling (especially for clinical notes)
- Patient context (for MIMIC-III integration)

---

## Common Issues & Solutions

### Issue: LLM not extracting species correctly
**Solution**: Check document header contains species mention. If not, LLM will default to "not specified" or infer from context.

### Issue: Species suffix duplicated in ontology_id
**Solution**: Fixed in code - checks if suffix already present before adding.

### Issue: EXTRACTED_FROM relationships not created
**Solution**: Ensure Source node created BEFORE loading entity nodes. Check `create_source_node()` called in Step 2.

### Issue: Relationships missing species fields
**Solution**: All relationships should have species via `apply_species_logic_to_relationship()`. Check this function is called in `process_text_chunk()`.

---

## Summary

This implementation adds:
- ✅ Document-level species and metadata extraction
- ✅ Species-aware entity and relationship processing
- ✅ Source provenance tracking via Source nodes
- ✅ EXTRACTED_FROM relationships for citation
- ✅ Updated Neo4j schema for multi-source knowledge aggregation
- ✅ RAG-ready context retrieval with source transparency

The system now accurately tracks which species findings apply to and can properly cite sources, making it suitable for production RAG applications in biomedical domains.

