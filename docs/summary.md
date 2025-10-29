# BioGraph: Medical Knowledge Graph Project Summary

## Executive Summary & Project Vision

### Project Goal
The BioGraph project creates a comprehensive, AI-ready biomedical knowledge graph by ingesting and structuring information from unstructured medical texts. The primary asset is the graph database itself, serving as a foundational backend for advanced applications including:
- **Clinician-facing diagnostic assistant**
- **Patient-facing symptom checker** 
- **Research and drug discovery platform**

### Core Strategy
The project employs a hybrid approach combining:
- **AI-Driven Extraction**: Large Language Models (LLMs) for flexible entity and relationship extraction based on rich, evolving schemas
- **Authoritative Standardization**: Established medical ontologies (UMLS, AWS Comprehend Medical) for data consistency and interoperability
- **Graph-Native Storage**: Neo4j database for effective storage and querying of complex, interconnected biomedical knowledge

## Architecture Overview

### MedGraph Flow Generation Pipeline
The system follows a sophisticated 5-stage enrichment pipeline that transforms unstructured medical text into a standardized knowledge graph:

#### Stage 1: Text Processing & Initial Extraction
- **Input**: Unstructured medical text (Biomedical_Knowledgebase.txt)
- **Text Chunking**: Splits documents into manageable paragraphs using LlamaIndex
- **LLM Entity/Relationship Extractor**: Uses AWS Bedrock (Claude Sonnet 4) to parse chunks and extract JSON-formatted medical entities and relationships

#### Stage 2: Enrichment Pipeline (4 Parallel Processes)
1. **3a. Abbreviation Expansion**: Resolves medical abbreviations using a curated abbreviation map (abbreviations.json)
2. **3b. Entity Standardization**: Maps entities to standard terminologies via AWS Comprehend Medical (SNOMED-CT for clinical concepts, RxNorm for medications)
3. **3c. Synonym Retrieval**: Fetches related terms from local UMLS PostgreSQL database
4. **3d. Vector Embedding Generation**: Creates semantic representations using OpenAI text-embedding-small model

#### Stage 3: Fallback & Quality Assurance
- **Fallback ID Generation**: Creates custom identifiers for entities that cannot be standardized to existing ontologies
- **Quality Control**: Ensures all entities receive proper identification and enrichment

#### Stage 4: Graph Database Loading
- **Neo4j Integration**: Loads enriched nodes and relationships into Neo4j database using idempotent MERGE queries
- **Relationship Mapping**: Maintains referential integrity between standardized entity IDs

### Data Flow Architecture
The pipeline leverages multiple external services and databases in a coordinated workflow:

#### External Knowledge Sources
- **SNOMED-CT**: Clinical terminology for diseases, symptoms, procedures, and anatomy
- **RxNorm**: Pharmaceutical terminology for medications and drug concepts
- **UMLS Database**: Unified Medical Language System providing comprehensive medical synonyms via local PostgreSQL instance

#### AI/ML Services Integration
- **AWS Comprehend Medical**: Provides standardized medical entity recognition and terminology mapping
- **AWS Bedrock (Claude Sonnet 4)**: Advanced LLM for intelligent parsing of medical text and entity/relationship extraction
- **OpenAI text-embedding-small**: Generates semantic vector representations for similarity search and concept matching

#### Processing Workflow
1. **Text Preprocessing**: Document chunking and preparation for LLM processing
2. **Parallel Enrichment**: Four concurrent processes handle abbreviation expansion, standardization, synonym retrieval, and embedding generation
3. **Quality Assurance**: Fallback mechanisms ensure complete entity coverage with custom identifiers when standard ontologies are insufficient
4. **Graph Construction**: Idempotent loading into Neo4j with relationship integrity maintenance

## Project Structure

### Core Components

#### 1. Data Processing Pipeline (`utils.py`)
- **Text Extraction**: Uses LLamaIndex for document splitting and processing
- **Entity Recognition**: LLM-powered extraction of medical entities and relationships
- **Standardization**: AWS Comprehend Medical integration for SNOMED-CT and RxNorm mapping
- **Knowledge Graph Construction**: Neo4j graph database storage with enriched entities

#### 2. API Service (`medical_kg_api_project/main.py`)
- **FastAPI-based REST API** (v3.7.0) for querying the knowledge graph
- **Multiple Query Types**:
  - Fuzzy search for autocomplete functionality
  - Natural language to Cypher query conversion
  - Semantic vector search
  - Synonym-based keyword expansion
  - Specialized medical relationship queries
- **Graph Visualization**: Node vicinity mapping for interactive exploration

#### 3. AWS Lambda Deployment
- **Serverless Architecture**: Lambda-ready with Mangum ASGI adapter
- **Layer Management**: Custom dependency layers for FastAPI, Neo4j, OpenAI
- **Environment Configuration**: Production-ready deployment scripts

### Technical Architecture

#### Data Schema & Ontology Design

##### Core Principles
- **One Concept, One Node**: Exactly one node per unique medical concept, identified by ontology_id
- **Properties for Nuance**: Attributes like dosage or severity stored as properties on nodes or relationships
- **Explicit Relationships**: All connections modeled as explicit, directed relationships

##### Node Ontology (18 Distinct Types)
- **Clinical Concepts**: Disease, Pathological_Finding, Symptom, Clinical_Finding, Side_Effect
- **Interventions**: Medication, Treatment, Diagnostic_Procedure, Medical_Device
- **Biological Concepts**: Anatomy, Pathogen, Gene, Protein, Genetic_Disorder, Biological_Process
- **Contextual Concepts**: Clinical_Study, Age_Group, Lifestyle_Factor, Environmental_Factor

##### Relationship Ontology (19 Types)
Including TREATED_BY, AFFECTS, CAUSED_BY, HAS_INDICATION, IS_A_TYPE_OF, HAS_SYMPTOM, DIAGNOSED_BY, PREVENTS, HAS_CONTRAINDICATION, HAS_COMPLICATION, HAS_SIDE_EFFECT, USES_MEDICATION, USES_DEVICE, METABOLIZED_BY, ASSOCIATED_WITH, CODES_FOR, STUDIED_IN, OCCURS_IN_AGE_GROUP, INCREASES_RISK_FOR

##### Standardized Node Properties
Every node adheres to a consistent property structure:
- **ontology_id** (String, Unique): Primary key from authoritative source (e.g., "SNOMEDCT:22298006") or fallback ID (e.g., "BIOGRAPH:LIFESTYLE_FACTOR:hash")
- **standard_name** (String): Official human-readable name from source ontology
- **synonyms** (List<String>): Comprehensive list of alternative names, abbreviations, and acronyms from UMLS
- **description** (String): Contextual description as extracted by LLM from source text
- **embedding** (List<Float>): Vector embedding for semantic search, indexed for performance

#### Technology Stack
- **Backend**: FastAPI, LLamaIndex, Neo4j Python Driver
- **AI/ML**: AWS Bedrock (Claude Sonnet 4), AWS Comprehend Medical, OpenAI text-embedding-small
- **Databases**: 
  - Neo4j Graph Database (primary knowledge graph storage)
  - PostgreSQL (local UMLS database for synonym expansion)
- **Cloud Services**: AWS Lambda, AWS Bedrock, AWS Comprehend Medical
- **Dependencies**: Pydantic for data validation, Mangum for serverless deployment

#### Pipeline Implementation Details
- **Batch Processing**: Configurable chunk sizes (~512 tokens with 20-token overlap for semantic coherence)
- **Confidence Thresholds**: Minimum 75% confidence score for AWS Comprehend Medical mappings (increased from 50%)
- **Fallback Strategy**: Deterministic SHA-1 based identifiers for unmappable entities (format: BIOGRAPH:{TYPE}:{hash})
- **Error Handling**: Comprehensive exception handling with graceful degradation
- **Idempotent Operations**: MERGE-based Neo4j queries prevent duplicate data insertion
  - Node Loading: `MERGE (n {ontology_id: $id}) SET n += {properties}`
  - Relationship Loading: `MATCH (source), (target) MERGE (source)-[r:REL_TYPE]->(target)`

### Key Features

#### 1. Intelligent Entity Extraction
- LLM-powered medical entity recognition from free text
- Context-aware entity typing and relationship mapping
- Comprehensive medical schema with 14 node types and 20+ relationship types

#### 2. Standardization & Enrichment
- AWS Comprehend Medical for SNOMED-CT/RxNorm mapping
- Synonym expansion and medical abbreviation handling
- Vector embeddings for semantic similarity

#### 3. Multi-Modal Querying
- **Search & Exploration**: Fuzzy search, detailed node inspection, graph vicinity mapping
- **Smart Querying**: Natural language to Cypher, semantic search, synonym expansion
- **Specialized Tools**: Disease-specific symptom/medication queries

#### 4. Production-Ready Deployment
- Dockerized Lambda deployment with optimized layers
- Environment-based configuration management
- Comprehensive batch processing scripts

### Data Sources
- **Primary**: Biomedical knowledge base text corpus
- **Standardization**: UMLS/SNOMED-CT via AWS Comprehend Medical
- **Processing**: Chunk-based pipeline with configurable batch sizes

### Development Environment
- **Jupyter Notebooks**: Interactive development and testing (`med_kb_dev.ipynb`)
- **Testing Framework**: Comprehensive unit tests for standardization and database loading
- **Local Development**: Neo4j Desktop integration for development

## Use Cases
1. **Medical Research**: Explore relationships between diseases, symptoms, and treatments
2. **Clinical Decision Support**: Query drug interactions, treatment options, diagnostic procedures
3. **Knowledge Discovery**: Semantic search across medical literature and guidelines
4. **Educational Tools**: Interactive exploration of medical concepts and relationships

## Implementation & Deployment Strategy

### Phase 1: Local Development & Cloud Deployment
The project follows a hybrid development strategy:
1. **Local Development**: Python ingestion script developed and tested against local Neo4j Desktop instance
2. **Cloud Deployment**: Once stable, pipeline points to Neo4j AuraDB cloud instance for full data ingestion

### Prerequisite Setup
One-time engineering setup requirements:
- UMLS database configuration and local PostgreSQL hosting
- AWS and LLM API credentials configuration  
- Local Python development environment establishment

## Technology Stack Rationale

| Component | Technology & Version | Selection Rationale |
|-----------|---------------------|-------------------|
| Data Storage | Neo4j (v5.x) Property Graph | Industry-leading native graph database with seamless Cypher integration and native vector search for AI/RAG applications |
| Data Extraction LLM | AWS Bedrock (Claude 4 Sonnet) | Strong performance in complex reasoning and structured JSON output, large context window for dense medical paragraphs |
| Data Standardization | AWS Comprehend Medical | HIPAA-eligible managed service with high-accuracy SNOMED-CT and RxNorm normalization |
| Terminology Source | UMLS Metathesaurus | Definitive "gold standard" for biomedical terminology |
| Vector Embeddings | OpenAI API (text-embedding-small) | Strong balance of performance and cost-efficiency for semantic vector embeddings |
| Orchestration | Python (v3.10+) | De facto language for data engineering and AI with mature libraries |
| UMLS Hosting | PostgreSQL (v15+) | Robust, open-source relational database for local UMLS MRCONSO.RRF hosting |

## Future Directions

### Schema Evolution
- Expand schema to include granular sub-types (e.g., `:Disease:Infectious_Disease`)
- Add new node types like `Medical_Organization`
- Continuous refinement based on domain expert feedback

### Application Layer Development
Once populated, the BioGraph database will serve as foundation for:
- **Professional RAG query engines** leveraging rich structure and vector embeddings
- **Advanced clinical decision support systems**
- **Research discovery platforms** for drug development and medical research

## Deployment Options
- **Local Development**: Neo4j Desktop + FastAPI dev server
- **Production**: AWS Lambda + Neo4j AuraDB cloud  
- **Hybrid**: Local Neo4j + Lambda API for cost optimization

This system represents a complete end-to-end solution for medical knowledge graph creation, management, and querying, designed for scalable deployment across research, clinical, and educational applications with enterprise-grade reliability and HIPAA compliance considerations.