import os
import json
import re
import hashlib
import time
from functools import wraps
from getpass import getpass
from concurrent.futures import ThreadPoolExecutor, as_completed

# Core libraries
import boto3  # For AWS Comprehend Medical
import psycopg2  # For connecting to the local UMLS PostgreSQL DB
import requests  # For making API calls to the LLM
from neo4j import GraphDatabase # The official Neo4j driver
from sentence_transformers import SentenceTransformer # For creating vector embeddings

# Recommended embedding models (in order of quality):
# 1. 'all-mpnet-base-v2' - Best balanced (768d, 420MB) ⭐ RECOMMENDED
# 2. 'BAAI/bge-large-en-v1.5' - Highest quality (1024d, 1.34GB)
# 3. 'BAAI/bge-small-en-v1.5' - Fast and good (384d, 133MB)
# 4. 'nomic-ai/nomic-embed-text-v1.5' - Great for scientific text (768d, 548MB)
# 5. 'all-MiniLM-L6-v2' - Fastest but lower quality (384d, 80MB) - CURRENT


# LlamaIndex components for text splitting
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter

print("All libraries imported successfully.")


# STEP 2: CONFIGURATION & SECRETS
#
# Best Practice: Store secrets in environment variables or a .env file,
# not directly in the code. We use os.getenv() to read them.
# =============================================================================
# --- LLM Configuration ---
# Replace with your chosen LLM API endpoint and key
LLM_API_URL = os.getenv("LLM_API_URL", "YOUR_LLM_API_ENDPOINT_HERE")
# LLM_API_KEY = os.getenv("LLM_API_KEY", getpass("Enter your LLM API Key: "))

# --- AWS Configuration ---
# Your Boto3 client will automatically use credentials from your environment
# (e.g., from `aws configure` or IAM role).
AWS_REGION = os.getenv("AWS_REGION", "us-east-1") # e.g., 'us-east-1'

# --- Neo4j Configuration ---
# Start with your local Neo4j Desktop instance for development.
# The script will prompt if environment variables are not set.
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = "qwerty123"
# NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", getpass("Enter your Neo4j Password: "))
NEO4J_DATABASE = "neo4j" # Default database

# --- PostgreSQL (UMLS) Configuration ---
UMLS_DB_NAME = os.getenv("UMLS_DB_NAME", "umls")
UMLS_DB_USER = os.getenv("UMLS_DB_USER", "postgres")
UMLS_DB_PASSWORD = os.getenv("UMLS_DB_PASSWORD", "qwerty123")  # UPDATE THIS
UMLS_DB_HOST = os.getenv("UMLS_DB_HOST", "localhost")
UMLS_DB_PORT = os.getenv("UMLS_DB_PORT", "5432")

# --- Source Data ---
SOURCE_DOCUMENT_PATH = "Biomedical_Knowledgebase.txt"
SOURCE_DOCUMENT_NAME = "Biomedical_Knowledgebase.txt"

print("Configuration loaded.")


# =============================================================================
# DOCUMENT CONTEXT & SPECIES CONFIGURATION
# =============================================================================

# Species-specific node types (species is part of entity identity)
SPECIES_SPECIFIC_NODE_TYPES = ['Gene', 'Protein', 'Anatomy', 'Cell_Type']

# Document context extraction prompt
DOCUMENT_CONTEXT_EXTRACTION_PROMPT = """
Analyze the beginning of this research paper and extract metadata in JSON format.

**TEXT (first 75 lines):**
{header_text}

**INSTRUCTIONS:**
Extract the following information:

1. **Bibliographic metadata:**
   - title: Full paper title
   - authors: Author list (format: "FirstAuthor, SecondAuthor, et al." - max 3 names)
   - journal: Journal or publication name
   - publication_year: Year only (YYYY format)
   - doi: DOI if present, otherwise null

2. **Species information:**
   - primary_species: Scientific name of PRIMARY organism studied
     * Look in Abstract and Methods sections
     * Examples: "Homo sapiens", "Mus musculus", "Rattus norvegicus"
     * If human clinical/medical context with no explicit mention: "Homo sapiens (implied)"
     * If computational/review with no specific organism: "not specified"
   - species_confidence: "high" (explicitly stated), "medium" (implied from context), "low" (unclear)
   - species_evidence: Brief quote showing where species was found (max 100 chars)

3. **Study type:**
   - study_type: "clinical trial" | "animal study" | "in vitro" | "computational" | "review" | "case report" | "other"

**IMPORTANT:**
- Return ONLY valid JSON, no other text
- If a field cannot be determined, use "Unknown" for strings or null for optional fields
- Use exact scientific names for species (capitalize genus, lowercase species epithet)

Return JSON:
{{
    "title": "string",
    "authors": "string",
    "journal": "string", 
    "publication_year": "YYYY",
    "doi": "string or null",
    "primary_species": "string",
    "species_confidence": "high|medium|low",
    "species_evidence": "string",
    "study_type": "string"
}}
"""

print("Document context configuration loaded.")


# =============================================================================
# RETRY DECORATOR FOR TRANSIENT FAILURES
# =============================================================================
def retry_on_failure(max_retries=3, initial_delay=1.0, backoff_factor=2.0, exceptions=(Exception,)):
    """
    Decorator to retry a function on failure with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds before first retry (default: 1.0)
        backoff_factor: Multiplier for delay after each retry (default: 2.0)
        exceptions: Tuple of exception types to catch and retry (default: all exceptions)
    
    Returns:
        Decorated function that retries on failure
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        print(f"  - ⚠️  Attempt {attempt + 1}/{max_retries + 1} failed: {str(e)[:100]}")
                        print(f"  - 🔄 Retrying in {delay:.1f}s...")
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        print(f"  - ❌ All {max_retries + 1} attempts failed")
                        raise last_exception
            
            # Should never reach here, but just in case
            raise last_exception
        return wrapper
    return decorator


# =============================================================================
# STEP 2.5: LLM INITIALIZATION
# Initialize AWS Bedrock LLM for entity extraction
# =============================================================================
def initialize_llm():
    """
    Initialize AWS Bedrock LLM (Claude 3.7 Sonnet) for medical entity extraction.
    Uses inference profile for on-demand access.
    Returns a LlamaIndex LLM object.
    """
    try:
        from llama_index.llms.bedrock import Bedrock
        
        # Use inference profile ID for on-demand access (not direct model ID)
        llm = Bedrock(
            model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",  # Inference profile
            region_name=AWS_REGION,
            temperature=0.1,
            max_tokens=8192,  # Increased to handle large entity/relationship lists
            context_size=200000,  # Claude 3.7 Sonnet has 200K context window
            additional_kwargs={
                "top_p": 0.9,
            }
        )
        print("✅ AWS Bedrock LLM (Claude 3.7 Sonnet) initialized successfully")
        return llm
    except Exception as e:
        print(f"❌ Error initializing Bedrock LLM: {e}")
        print("\n💡 Troubleshooting:")
        print("  1. Check AWS credentials: aws sts get-caller-identity")
        print("  2. Check Bedrock access in us-east-1 region")
        print("  3. Verify inference profile access:")
        print("     aws bedrock list-inference-profiles --region us-east-1")
        print("  4. Model access may need to be enabled in Bedrock console")
        raise RuntimeError(f"Could not initialize AWS Bedrock LLM: {e}")

print("LLM initialization function defined.")


def initialize_llm_lmstudio(base_url="http://127.0.0.1:1234/v1", model_name="qwen3-30b-a3b-2507"):
    """
    Initialize LM Studio local LLM server for medical entity extraction.
    
    Args:
        base_url: LM Studio server URL (default: http://127.0.0.1:1234/v1)
        model_name: Model identifier (for display/logging purposes)
    
    Returns:
        A wrapper object compatible with LlamaIndex LLM interface
    """
    try:
        from openai import OpenAI
        
        # Create OpenAI client pointing to LM Studio
        client = OpenAI(
            base_url=base_url,
            api_key="lm-studio"  # Dummy key for local server
        )
        
        # Test connection
        try:
            models = client.models.list()
            available_models = [m.id for m in models.data]
            print(f"✅ LM Studio server connected: {base_url}")
            print(f"   Available models: {', '.join(available_models)}")
        except Exception as e:
            print(f"⚠️  Could not list models (server may be busy): {e}")
        
        # Create a wrapper to make it compatible with LlamaIndex interface
        class LMStudioLLM:
            def __init__(self, client, model_name):
                self.client = client
                self.model_name = model_name
                self.temperature = 0.7
                self.max_tokens = 8192  # Match Claude's setting - prevents JSON truncation (Qwen3 supports up to 32K)
                
            def complete(self, prompt, **kwargs):
                """Complete a prompt (LlamaIndex-compatible interface)"""
                # Override defaults with any provided kwargs
                temperature = kwargs.get('temperature', self.temperature)
                max_tokens = kwargs.get('max_tokens', self.max_tokens)
                
                try:
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=temperature,
                        max_tokens=max_tokens,
                        top_p=0.8,
                        # Note: top_k not supported by LM Studio's OpenAI-compatible API
                    )
                    
                    # Create a response object with .text attribute
                    class Response:
                        def __init__(self, text):
                            self.text = text
                    
                    return Response(response.choices[0].message.content)
                    
                except Exception as e:
                    print(f"  - ❌ LM Studio API error: {e}")
                    raise
        
        llm_wrapper = LMStudioLLM(client, model_name)
        print(f"✅ LLM initialized successfully (LM Studio - {model_name})")
        print(f"   Server: {base_url}")
        print(f"   Settings: temp={llm_wrapper.temperature}, max_tokens={llm_wrapper.max_tokens}")
        return llm_wrapper
        
    except ImportError:
        print("❌ OpenAI package not installed. Run: pip install openai")
        raise
    except Exception as e:
        print(f"❌ Error initializing LM Studio LLM: {e}")
        print(f"   Make sure LM Studio server is running at {base_url}")
        raise

print("LM Studio LLM initialization function defined.")


# =============================================================================
# DOCUMENT CONTEXT EXTRACTION FUNCTIONS
# =============================================================================

@retry_on_failure(max_retries=3, initial_delay=2.0)
def extract_document_context(file_path, source_id, llm):
    """
    Extract complete document context (metadata + species) in single LLM call.
    
    Args:
        file_path: Path to the document text file
        source_id: Unique identifier for the source (e.g., "PMC8675309")
        llm: Initialized LLM instance
        
    Returns:
        dict: Complete document context with metadata and species information
    """
    from datetime import datetime
    from pathlib import Path
    
    # Read first 75 lines from document
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            header_lines = []
            for _ in range(75):
                line = f.readline()
                if not line:
                    break
                header_lines.append(line)
            header_text = ''.join(header_lines)
    except Exception as e:
        print(f"  ⚠️  Error reading file {file_path}: {e}")
        raise
    
    # Extract metadata via LLM
    prompt = DOCUMENT_CONTEXT_EXTRACTION_PROMPT.format(header_text=header_text)
    
    try:
        response = llm.complete(prompt)
        response_text = response.text if hasattr(response, 'text') else str(response)
        
        # Clean response (remove markdown code blocks if present)
        response_text = response_text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        metadata = json.loads(response_text)
        
        # Add additional fields
        metadata['source_id'] = source_id
        metadata['source_type'] = 'research_article'
        metadata['source_platform'] = 'PubMed Central'
        metadata['processing_date'] = datetime.now().isoformat()
        metadata['document_path'] = str(Path(file_path).absolute())
        
        return metadata
        
    except json.JSONDecodeError as e:
        print(f"  ⚠️  Failed to parse document context JSON: {e}")
        print(f"  Using safe defaults for {source_id}")
        # Return safe defaults
        return {
            'source_id': source_id,
            'title': 'Unknown',
            'authors': 'Unknown',
            'journal': 'Unknown',
            'publication_year': 'Unknown',
            'doi': None,
            'primary_species': 'not specified',
            'species_confidence': 'low',
            'species_evidence': 'Unable to extract',
            'study_type': 'other',
            'source_type': 'research_article',
            'source_platform': 'PubMed Central',
            'processing_date': datetime.now().isoformat(),
            'document_path': str(Path(file_path).absolute())
        }


def apply_species_logic_to_node(node, document_context):
    """
    Apply species handling rules to extracted nodes.
    Species-specific node types get species in their identity.
    
    Args:
        node: Dict representing an extracted entity
        document_context: Document metadata with species info
        
    Returns:
        dict: Node with correct species handling applied
    """
    node_type = node.get('entity_type', '')
    
    # Check if this node type is species-specific
    if node_type in SPECIES_SPECIFIC_NODE_TYPES:
        # Species IS part of identity
        if 'species' not in node or not node['species']:
            node['species'] = document_context['primary_species']
            node['species_confidence'] = 'inherited'
        
        # Mark that this node needs species in ontology_id (will be added after standardization)
        node['_needs_species_suffix'] = True
    else:
        # Species is NOT part of identity - remove from node if present
        node.pop('species', None)
        node.pop('species_confidence', None)
        node['_needs_species_suffix'] = False
    
    return node


def apply_species_logic_to_relationship(rel, document_context):
    """
    Ensure all relationships have species metadata.
    
    Args:
        rel: Dict representing an extracted relationship
        document_context: Document metadata with species info
        
    Returns:
        dict: Relationship with species fields populated
    """
    # Always require species in relationships
    if 'species' not in rel or not rel['species']:
        rel['species'] = document_context['primary_species']
        rel['species_confidence'] = 'inherited'
    
    # Validate species_confidence
    if 'species_confidence' not in rel or not rel['species_confidence']:
        rel['species_confidence'] = 'inherited'
    
    return rel


print("Document context extraction functions defined.")


# =============================================================================
# STEP 3: DEFINE THE COMPREHENSIVE SCHEMA (v1.5)
# This schema will be used in our LLM prompt.
# =============================================================================
COMPREHENSIVE_SCHEMA = {
    "node_types": [
        # --- Clinical Concepts ---
        "Disease",              # A specific illness, disorder, or abnormal medical condition (e.g., "Hypertension", "ADHD"). Includes general conditions.
        "Pathological_Finding", # An objective, structural or functional abnormality found via examination or testing (e.g., "Aortic aneurysm", "Gallstones").
        "Symptom",              # A subjective experience reported by a patient (e.g., "headache", "dizziness", "low self-esteem").
        "Clinical_Finding",     # An objective sign observed or measured by a clinician (e.g., "aggressive behavior", "high white blood cell count").
        "Side_Effect",          # An adverse reaction or unintended consequence of a medication or treatment (e.g., "insomnia", "nausea"). Includes complications.

        # --- Interventions ---
        "Medication",           # A specific drug or pharmaceutical substance (e.g., "Ritalin", "Lisinopril").
        "Treatment",            # A therapeutic regimen or procedure that is not a drug (e.g., "psychiatric hospital", "acupuncture").
        "Diagnostic_Procedure", # A test, scan, or method used to diagnose a condition (e.g., "Abdominal ultrasound", "biopsy").
        "Medical_Device",       # A physical tool or instrument used in a medical procedure (e.g., "ultrasound probe", "pacemaker").

        # --- Biological & Genetic Concepts ---
        "Anatomy",              # A specific body part, organ, or physiological system (e.g., "liver", "abdominal aorta").
        "Pathogen",             # An infectious agent that causes disease (e.g., "Bacillus anthracis").
        "Gene",                 # A specific gene involved in biological processes or diseases (e.g., "NF2 gene").
        "Protein",              # A specific protein molecule.
        "Genetic_Disorder",     # A disease specifically caused by genetic abnormalities (e.g., "Achondroplasia").
        "Biological_Process",   # A physiological or cellular mechanism (e.g., "inflammation", "liver metabolism").

        # --- Contextual & Epidemiological Concepts ---
        "Clinical_Study",       # A formal research investigation, trial, or study (e.g., "randomized controlled trial").
        "Age_Group",            # A specific patient population defined by age (e.g., "children", "elderly").
        "Lifestyle_Factor",     # A behavioral factor that influences health (e.g., "Smoking", "Alcohol consumption").
        "Environmental_Factor", # An external, non-behavioral factor that influences health (e.g., "home environment", "asbestos exposure").
    ],
    "relationship_types": [
        # --- Hierarchical & Definitional ---
        "IS_A_TYPE_OF",         # Creates a hierarchy between concepts (e.g., (:B-mode_ultrasound)-[:IS_A_TYPE_OF]->(:Ultrasound)).
        "PRESENTS_AS",          # Links a disease to its objective manifestation (e.g., (:Gallbladder_Disease)-[:PRESENTS_AS]->(:Gallstones)).

        # --- Clinical Relationships ---
        "HAS_SYMPTOM",          # Connects a disease to a subjective symptom (e.g., (:Migraine)-[:HAS_SYMPTOM]->(:Headache)).
        "HAS_FINDING",          # Connects a disease to an objective clinical sign (e.g., (:Jaundice)-[:HAS_FINDING]->(:Yellow_Skin)).
        "TREATED_BY",           # Connects a disease to a medication or treatment that manages or cures it.
        "PREVENTS",             # Connects an intervention to a disease it can prevent (e.g., (:Vaccination)-[:PREVENTS]->(:Measles)).
        "DIAGNOSED_BY",         # Connects a disease to a procedure used to identify it.
        "HAS_INDICATION",       # Connects a procedure/treatment to the condition it is used for (e.g., (:Ultrasound)-[:HAS_INDICATION]->(:Abdominal_Pain)).
        "HAS_CONTRAINDICATION", # Connects a procedure/treatment to a condition where it would be harmful.
        "HAS_COMPLICATION",     # Connects a treatment/procedure to a potential negative outcome.
        "HAS_SIDE_EFFECT",      # Connects a medication to a known adverse reaction.
        "USES_MEDICATION",      # Connects a treatment regimen to a specific drug it involves (e.g., (:Chemotherapy)-[:USES_MEDICATION]->(:Cisplatin)).
        "USES_DEVICE",          # Connects a procedure to a medical device it requires.

        # --- Biological & Causal Relationships ---
        "AFFECTS",              # Connects a disease or process to the anatomy it impacts (e.g., (:Hepatitis)-[:AFFECTS]->(:Liver)).
        "CAUSED_BY",            # Connects a disease to its direct etiological cause (e.g., (:Anthrax)-[:CAUSED_BY]->(:Bacillus_anthracis)).
        "INCREASES_RISK_FOR",   # Connects a risk factor to a disease (e.g., (:Smoking)-[:INCREASES_RISK_FOR]->(:Lung_Cancer)).
        "METABOLIZED_BY",       # Connects a medication to a biological process (e.g., (:Acetaminophen)-[:METABOLIZED_BY]->(:Liver_Enzyme_Activity)).
        "ASSOCIATED_WITH",      # Connects a gene to a genetic disorder.
        "CODES_FOR",            # Connects a gene to the protein it creates.

        # --- Contextual Relationships ---
        "STUDIED_IN",           # Connects a concept (like a drug or treatment) to the clinical study that investigated it.
        "OCCURS_IN_AGE_GROUP",  # Connects a disease to a specific age population.
    ]
}

print("Comprehensive schema defined.")

# =============================================================================
# STEP 4: DEFINE THE LLM EXTRACTION PROMPT
# =============================================================================
# =============================================================================
# CORRECTED AND IMPROVED LLM PROMPT TEMPLATE
# =============================================================================

# =============================================================================
# FINAL AND MOST ROBUST LLM PROMPT TEMPLATE (v1.2)
# =============================================================================

# =============================================================================
# FINAL AND MOST ROBUST LLM PROMPT TEMPLATE (v1.3)
# =============================================================================

EXTRACTION_PROMPT_TEMPLATE = """
-GOAL-
You are a world-class biomedical informatics expert. Your task is to act as a precision knowledge extraction engine from a given medical text document. Identify all relevant medical entities and their relationships according to the provided schema.

-DOCUMENT CONTEXT-
**Source:** {source_title}
**Journal:** {source_journal} ({source_year})
**Primary Species Studied:** {document_species}
**Study Type:** {study_type}

-SCHEMA DEFINITION-
Node Types: {node_types}
Relationship Types: {relationship_types}

-CRITICAL INSTRUCTIONS-
**ALWAYS expand medical abbreviations to their full terms:**
- Use complete medical terminology, never abbreviations
- Example: "MI" → "Myocardial Infarction"
- Example: "COPD" → "Chronic Obstructive Pulmonary Disease"
- Example: "BP" → "Blood Pressure"
- Example: "CT" → "Computed Tomography"
- Example: "MRI" → "Magnetic Resonance Imaging"
- If unsure about an abbreviation, use your best medical knowledge based on context

**SPECIES HANDLING RULES:**

For ENTITIES:
- For node types: Gene, Protein, Anatomy, Cell_Type → INCLUDE "species" field
  Example: {{"entity_name": "TP53", "entity_type": "Gene", "species": "Homo sapiens", ...}}
  
- For node types: Drug, Disease, Treatment, Symptom, Medication, Biological_Process, Pathogen, etc. → DO NOT include "species" field
  Example: {{"entity_name": "Aspirin", "entity_type": "Drug", ...}}  ← No species field

For RELATIONSHIPS:
- ALWAYS include "species" and "species_confidence" fields
- Default species: {document_species}
- **species_confidence** options:
  * "explicit": Species is directly mentioned in the text chunk
  * "inherited": Species not mentioned in chunk, using document default ({document_species})
  * "speculative": Discussing hypothetical cross-species implications
  * "unknown": Cannot determine species

Examples:
- Chunk says "In mice, drug X reduced tumors" → species: "Mus musculus", species_confidence: "explicit"
- Chunk says "Drug X reduced tumors" (no species mentioned) → species: "{document_species}", species_confidence: "inherited"
- Chunk says "This may be applicable to humans" → species: "Homo sapiens", species_confidence: "speculative"

-EXTRACTION STEPS-
1.  **Identify Entities:** Carefully read the text and identify all terms that match one of the node types in the schema. For each entity, you must extract:
    - `entity_name`: **ALWAYS use the fully expanded medical term, never abbreviations**
    - `entity_type`: The corresponding type from the schema's Node Types list.
    - `entity_description`: A concise, one-sentence description of the entity based on its context in the text.
    - `species`: ONLY for Gene, Protein, Anatomy, Cell_Type entities (see SPECIES HANDLING RULES above)

2.  **Identify Relationships:** Identify all relationships between the entities you found. The relationship must match one of the types in the schema. For each relationship, you must extract:
    - `source_entity_name`: The name of the source entity.
    - `source_entity_type`: The type of the source entity.
    - `target_entity_name`: The name of the target entity.
    - `target_entity_type`: The type of the target entity.
    - `relation_type`: The corresponding type from the schema's Relationship Types list.
    - `relationship_description`: A concise, one-sentence explanation of the relationship based on the text.
    - `species`: The species this relationship applies to (REQUIRED - see SPECIES HANDLING RULES)
    - `species_confidence`: How certain the species assignment is (REQUIRED - see SPECIES HANDLING RULES)

-OUTPUT FORMATTING-
1.  **CRITICAL:** Your entire response must be ONLY a single, valid JSON object. Do not include any introductory text, greetings, or markdown formatting like ```json.
2.  The JSON object must have two primary keys: "entities" and "relationships".
3.  The value for each key must be a list of JSON objects, where each object follows the structure defined in the EXTRACTION STEPS.
4.  If no entities or relationships are found, return an empty list for the corresponding key.

-EXAMPLE OF THE EXACT JSON STRUCTURE REQUIRED-
```json
{{
  "entities": [
    {{"entity_name": "Aspirin", "entity_type": "Drug", "entity_description": "A common pain reliever and anti-inflammatory medication."}},
    {{"entity_name": "TP53", "entity_type": "Gene", "species": "Homo sapiens", "entity_description": "A tumor suppressor gene that regulates cell division."}}
  ],
  "relationships": [
    {{"source_entity_name": "Aspirin", "source_entity_type": "Drug", "target_entity_name": "Inflammation", "target_entity_type": "Pathological_Finding", "relation_type": "TREATS", "relationship_description": "Aspirin reduces inflammation by inhibiting prostaglandin synthesis.", "species": "Homo sapiens", "species_confidence": "inherited"}}
  ]
}}
```
-MEDICAL TEXT TO ANALYZE-
{text_chunk}

-FINAL JSON OUTPUT-
"""

# We format the prompt with the schema details when we use it
# PROMPT_WITH_SCHEMA = EXTRACTION_PROMPT_TEMPLATE.format(
#     node_types=', '.join(COMPREHENSIVE_SCHEMA['node_types']),
#     relationship_types=', '.join(COMPREHENSIVE_SCHEMA['relationship_types'])
# )

# And in your process_text_chunk function, you'll now use it like this:
# prompt = PROMPT_WITH_SCHEMA.format(text_chunk=text_chunk)

print("LLM prompt template created.")


# =============================================================================
# STEP 5: THE ENRICHMENT PIPELINE
# These functions will perform the Standardization, Synonym, and Embedding steps.
# =============================================================================

# --- 5a. Standardization ---

# =============================================================================
# REVISED AND IMPROVED STANDARDIZATION FUNCTION
# =============================================================================

# Define which entity types should be processed by which AWS API.
# Now includes ALL entity types with educated guesses + fallback mechanism
ENTITY_TYPE_TO_API_MAP = {
    # Clinical Concepts - SNOMED CT
    "Disease": "snomed",
    "Pathological_Finding": "snomed",
    "Symptom": "snomed",
    "Clinical_Finding": "snomed",
    "Side_Effect": "snomed",
    
    # Interventions - Mixed
    "Medication": "rxnorm",           # Definitely RxNorm
    "Treatment": "snomed",            # Medical procedures/therapies
    "Diagnostic_Procedure": "snomed", # Tests, scans, etc.
    "Medical_Device": "snomed",       # Instruments, tools
    
    # Biological & Genetic Concepts - SNOMED CT (best guess)
    "Anatomy": "snomed",
    "Pathogen": "snomed",             # Infectious organisms
    "Gene": "snomed",                 # Best guess, might fallback
    "Protein": "snomed",              # Best guess, might fallback  
    "Genetic_Disorder": "snomed",     # Hereditary conditions
    "Biological_Process": "snomed",   # Physiological processes
    
    # Contextual Concepts - SNOMED CT (educated guesses)
    "Clinical_Study": "snomed",       # Research terminology
    "Age_Group": "snomed",            # Demographics in SNOMED
    "Lifestyle_Factor": "snomed",     # Behavioral factors
    "Environmental_Factor": "snomed", # External factors
}
MIN_CONFIDENCE_SCORE = 0.75 # Higher threshold since we now try both APIs - filters false positives better

def generate_fallback_id(entity_name: str, entity_type: str) -> str:
    """Creates a deterministic, project-specific ID for unlinked entities."""
    normalized_name = re.sub(r'[^a-z0-9]', '', entity_name.lower())
    # Use a consistent hash function
    hashed_id = hashlib.sha1(normalized_name.encode()).hexdigest()[:12]
    return f"BIOGRAPH:{entity_type.upper()}:{hashed_id}"


# =============================================================================
# COMPREHENSIVE MEDICAL ABBREVIATION DICTIONARY
# 200+ common medical abbreviations for fallback expansion
# Note: LLM does primary expansion (context-aware), this is backup
# =============================================================================
ABBREVIATION_MAP = {
    # ========== CARDIOVASCULAR ==========
    "MI": "Myocardial Infarction",
    "CHF": "Congestive Heart Failure",
    "AF": "Atrial Fibrillation",
    "AFib": "Atrial Fibrillation",
    "CAD": "Coronary Artery Disease",
    "PVD": "Peripheral Vascular Disease",
    "DVT": "Deep Vein Thrombosis",
    "PE": "Pulmonary Embolism",
    "HTN": "Hypertension",
    "HBP": "High Blood Pressure",
    "CABG": "Coronary Artery Bypass Graft",
    "PCI": "Percutaneous Coronary Intervention",
    "STEMI": "ST-Elevation Myocardial Infarction",
    "NSTEMI": "Non-ST-Elevation Myocardial Infarction",
    "SVT": "Supraventricular Tachycardia",
    "VT": "Ventricular Tachycardia",
    "VF": "Ventricular Fibrillation",
    
    # ========== RESPIRATORY ==========
    "COPD": "Chronic Obstructive Pulmonary Disease",
    "ARDS": "Acute Respiratory Distress Syndrome",
    "URI": "Upper Respiratory Infection",
    "URTI": "Upper Respiratory Tract Infection",
    "LRTI": "Lower Respiratory Tract Infection",
    "OSA": "Obstructive Sleep Apnea",
    "TB": "Tuberculosis",
    "CF": "Cystic Fibrosis",
    "IPF": "Idiopathic Pulmonary Fibrosis",
    "SOB": "Shortness of Breath",
    "DOE": "Dyspnea on Exertion",
    
    # ========== NEUROLOGICAL ==========
    "CVA": "Cerebrovascular Accident",
    "TIA": "Transient Ischemic Attack",
    "ICH": "Intracranial Hemorrhage",
    "SAH": "Subarachnoid Hemorrhage",
    "MS": "Multiple Sclerosis",
    "ALS": "Amyotrophic Lateral Sclerosis",
    "PD": "Parkinson's Disease",
    "AD": "Alzheimer's Disease",
    "SCI": "Spinal Cord Injury",
    "TBI": "Traumatic Brain Injury",
    "CP": "Cerebral Palsy",
    "LOC": "Loss of Consciousness",
    "AMS": "Altered Mental Status",
    
    # ========== PSYCHIATRIC ==========
    "ADHD": "Attention-Deficit Hyperactivity Disorder",
    "OCD": "Obsessive-Compulsive Disorder",
    "PTSD": "Post-Traumatic Stress Disorder",
    "GAD": "Generalized Anxiety Disorder",
    "MDD": "Major Depressive Disorder",
    "BPD": "Borderline Personality Disorder",
    "SAD": "Seasonal Affective Disorder",
    "BD": "Bipolar Disorder",
    "CD": "Conduct Disorder",
    "ODD": "Oppositional Defiant Disorder",
    
    # ========== GASTROINTESTINAL ==========
    "GERD": "Gastroesophageal Reflux Disease",
    "IBD": "Inflammatory Bowel Disease",
    "IBS": "Irritable Bowel Syndrome",
    "UC": "Ulcerative Colitis",
    "PUD": "Peptic Ulcer Disease",
    "NASH": "Non-Alcoholic Steatohepatitis",
    "NAFLD": "Non-Alcoholic Fatty Liver Disease",
    "GI": "Gastrointestinal",
    "N/V": "Nausea and Vomiting",
    "LFT": "Liver Function Test",
    
    # ========== ENDOCRINE/METABOLIC ==========
    "DM": "Diabetes Mellitus",
    "T1DM": "Type 1 Diabetes Mellitus",
    "T2DM": "Type 2 Diabetes Mellitus",
    "DKA": "Diabetic Ketoacidosis",
    "HHS": "Hyperosmolar Hyperglycemic State",
    "HbA1c": "Glycated Hemoglobin",
    "TSH": "Thyroid Stimulating Hormone",
    "BMI": "Body Mass Index",
    "MetS": "Metabolic Syndrome",
    
    # ========== RENAL/URINARY ==========
    "CKD": "Chronic Kidney Disease",
    "AKI": "Acute Kidney Injury",
    "ESRD": "End-Stage Renal Disease",
    "UTI": "Urinary Tract Infection",
    "BPH": "Benign Prostatic Hyperplasia",
    "PKD": "Polycystic Kidney Disease",
    "ARF": "Acute Renal Failure",
    "CRF": "Chronic Renal Failure",
    
    # ========== HEMATOLOGY/ONCOLOGY ==========
    "ALL": "Acute Lymphoblastic Leukemia",
    "AML": "Acute Myeloid Leukemia",
    "CLL": "Chronic Lymphocytic Leukemia",
    "CML": "Chronic Myeloid Leukemia",
    "NHL": "Non-Hodgkin Lymphoma",
    "HL": "Hodgkin Lymphoma",
    "MM": "Multiple Myeloma",
    "MDS": "Myelodysplastic Syndrome",
    "ITP": "Immune Thrombocytopenic Purpura",
    "DIC": "Disseminated Intravascular Coagulation",
    "HIT": "Heparin-Induced Thrombocytopenia",
    
    # ========== INFECTIOUS DISEASE ==========
    "HIV": "Human Immunodeficiency Virus",
    "AIDS": "Acquired Immunodeficiency Syndrome",
    "HCV": "Hepatitis C Virus",
    "HBV": "Hepatitis B Virus",
    "HAV": "Hepatitis A Virus",
    "HSV": "Herpes Simplex Virus",
    "CMV": "Cytomegalovirus",
    "EBV": "Epstein-Barr Virus",
    "MRSA": "Methicillin-Resistant Staphylococcus Aureus",
    "VRE": "Vancomycin-Resistant Enterococcus",
    "C diff": "Clostridioides difficile",
    "STI": "Sexually Transmitted Infection",
    "STD": "Sexually Transmitted Disease",
    
    # ========== RHEUMATOLOGY/IMMUNOLOGY ==========
    "RA": "Rheumatoid Arthritis",
    "OA": "Osteoarthritis",
    "SLE": "Systemic Lupus Erythematosus",
    "AS": "Ankylosing Spondylitis",
    "PSA": "Psoriatic Arthritis",
    "SS": "Sjogren's Syndrome",
    "MCTD": "Mixed Connective Tissue Disease",
    "GCA": "Giant Cell Arteritis",
    "PMR": "Polymyalgia Rheumatica",
    
    # ========== DIAGNOSTIC IMAGING ==========
    "CT": "Computed Tomography",
    "MRI": "Magnetic Resonance Imaging",
    "PET": "Positron Emission Tomography",
    "US": "Ultrasound",
    "CXR": "Chest X-Ray",
    "KUB": "Kidneys Ureters Bladder",
    "ERCP": "Endoscopic Retrograde Cholangiopancreatography",
    "EGD": "Esophagogastroduodenoscopy",
    "MRCP": "Magnetic Resonance Cholangiopancreatography",
    
    # ========== PROCEDURES ==========
    "CPR": "Cardiopulmonary Resuscitation",
    "EKG": "Electrocardiogram",
    "ECG": "Electrocardiogram",
    "EEG": "Electroencephalogram",
    "EMG": "Electromyography",
    "LP": "Lumbar Puncture",
    "I&D": "Incision and Drainage",
    "D&C": "Dilation and Curettage",
    "TURP": "Transurethral Resection of Prostate",
    
    # ========== MEDICATIONS/DRUG CLASSES ==========
    "NSAID": "Non-Steroidal Anti-Inflammatory Drug",
    "ACE": "Angiotensin-Converting Enzyme",
    "ARB": "Angiotensin Receptor Blocker",
    "CCB": "Calcium Channel Blocker",
    "BB": "Beta Blocker",
    "SSRI": "Selective Serotonin Reuptake Inhibitor",
    "SNRI": "Serotonin-Norepinephrine Reuptake Inhibitor",
    "TCA": "Tricyclic Antidepressant",
    "MAOI": "Monoamine Oxidase Inhibitor",
    "PPI": "Proton Pump Inhibitor",
    "H2RA": "Histamine-2 Receptor Antagonist",
    "LMWH": "Low Molecular Weight Heparin",
    "DOAC": "Direct Oral Anticoagulant",
    "DMARD": "Disease-Modifying Antirheumatic Drug",
    "TNF": "Tumor Necrosis Factor",
    "IV": "Intravenous",
    "IM": "Intramuscular",
    "SQ": "Subcutaneous",
    "PO": "Per Os (by mouth)",
    "PR": "Per Rectum",
    "SL": "Sublingual",
    
    # ========== VITAL SIGNS/MEASUREMENTS ==========
    "BP": "Blood Pressure",
    "HR": "Heart Rate",
    "RR": "Respiratory Rate",
    "SpO2": "Oxygen Saturation",
    "Temp": "Temperature",
    "BS": "Blood Sugar",
    "BG": "Blood Glucose",
    "ABG": "Arterial Blood Gas",
    "VBG": "Venous Blood Gas",
    
    # ========== LAB VALUES ==========
    "CBC": "Complete Blood Count",
    "CMP": "Comprehensive Metabolic Panel",
    "BMP": "Basic Metabolic Panel",
    "LFT": "Liver Function Test",
    "PT": "Prothrombin Time",
    "PTT": "Partial Thromboplastin Time",
    "INR": "International Normalized Ratio",
    "ESR": "Erythrocyte Sedimentation Rate",
    "CRP": "C-Reactive Protein",
    "BNP": "B-type Natriuretic Peptide",
    "Trop": "Troponin",
    "PSA": "Prostate-Specific Antigen",
    "TSH": "Thyroid Stimulating Hormone",
    "T3": "Triiodothyronine",
    "T4": "Thyroxine",
    "WBC": "White Blood Cell",
    "RBC": "Red Blood Cell",
    "Hgb": "Hemoglobin",
    "Hct": "Hematocrit",
    "PLT": "Platelet",
    
    # ========== SYMPTOMS/FINDINGS ==========
    "SOB": "Shortness of Breath",
    "CP": "Chest Pain",
    "HA": "Headache",
    "N/V": "Nausea/Vomiting",
    "D/C": "Discontinue",
    "C/O": "Complains Of",
    "R/O": "Rule Out",
    "H/O": "History Of",
    "S/P": "Status Post",
    
    # ========== SPECIALTIES ==========
    "ED": "Emergency Department",
    "ER": "Emergency Room",
    "ICU": "Intensive Care Unit",
    "CCU": "Cardiac Care Unit",
    "NICU": "Neonatal Intensive Care Unit",
    "PICU": "Pediatric Intensive Care Unit",
    "OR": "Operating Room",
    "PACU": "Post-Anesthesia Care Unit",
    "OB": "Obstetrics",
    "GYN": "Gynecology",
    "ENT": "Ear Nose Throat",
    
    # ========== OTHER COMMON ==========
    "PRN": "As Needed",
    "QD": "Once Daily",
    "BID": "Twice Daily",
    "TID": "Three Times Daily",
    "QID": "Four Times Daily",
    "HS": "At Bedtime",
    "AC": "Before Meals",
    "PC": "After Meals",
    "NPO": "Nothing By Mouth",
    "DNR": "Do Not Resuscitate",
    "DNI": "Do Not Intubate",
    "AMA": "Against Medical Advice",
    "ADL": "Activities of Daily Living",
    "ROM": "Range of Motion",
    "PT": "Physical Therapy",
    "OT": "Occupational Therapy",
    "HPI": "History of Present Illness",
    "PMH": "Past Medical History",
    "PSH": "Past Surgical History",
    "FH": "Family History",
    "SH": "Social History",
}

def clean_description(description: str) -> str:
    """Removes the semantic tag like (finding) from the end of a description."""
    return re.sub(r'\s\([^)]+\)$', '', description).strip()

# =============================================================================
# FINAL, MOST ROBUST STANDARDIZATION FUNCTION (v1.4 - Context-Aware)
# =============================================================================

def batch_standardize_entities(entities: list, aws_client, max_workers: int = 4) -> dict:
    """
    Standardize multiple entities using PARALLEL AWS Comprehend calls.
    Uses ThreadPoolExecutor for concurrent API calls (4-8x speedup).
    
    Args:
        entities: List of entity dicts with 'entity_name' and 'entity_type'
        aws_client: boto3 comprehendmedical client
        max_workers: Number of parallel workers (default: 4, safe for 20 TPS limit)
    
    Returns:
        Dict mapping (entity_name, entity_type) -> standardization result
    """
    if not entities:
        return {}
    
    results = {}
    
    # Helper function for thread execution
    def standardize_single_entity(entity):
        """Wrapper to standardize a single entity with error handling."""
        entity_name = entity.get('entity_name', '')
        entity_type = entity.get('entity_type', '')
        entity_key = (entity_name, entity_type)
        
        try:
            standard_info = standardize_entity(entity_name, entity_type, aws_client)
            return entity_key, standard_info, None
        except Exception as e:
            # Return error, will use fallback
            return entity_key, None, e
    
    # Execute standardization calls in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_entity = {
            executor.submit(standardize_single_entity, entity): entity
            for entity in entities
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_entity):
            entity = future_to_entity[future]
            
            try:
                entity_key, standard_info, error = future.result()
                
                if error:
                    # Error occurred, use fallback
                    entity_name = entity.get('entity_name', '')
                    entity_type = entity.get('entity_type', '')
                    print(f"  - ⚠️  AWS Comprehend error for '{entity_name}': {str(error)[:100]}")
                    results[entity_key] = {
                        'ontology_id': generate_fallback_id(entity_name, entity_type),
                        'standard_name': entity_name.title()
                    }
                else:
                    # Success
                    results[entity_key] = standard_info
                    
            except Exception as e:
                # Unexpected error in future itself
                entity_name = entity.get('entity_name', '')
                entity_type = entity.get('entity_type', '')
                entity_key = (entity_name, entity_type)
                results[entity_key] = {
                    'ontology_id': generate_fallback_id(entity_name, entity_type),
                    'standard_name': entity_name.title()
                }
    
    return results


@retry_on_failure(max_retries=2, initial_delay=0.5, exceptions=(Exception,))
def standardize_entity(entity_name: str, entity_type: str, aws_client) -> dict:
    """
    Enhanced standardization with dual-API fallback mechanism.
    
    Strategy:
    1. Try primary API (SNOMED or RxNorm based on entity type)
    2. If no confident match, try secondary API (the other one)  
    3. Confidence scoring filters false positives
    4. Final fallback to deterministic ID
    
    Note: Has retry logic (2 retries) to handle AWS rate limiting/timeouts
    """
    # 1. Abbreviation Expansion
    expanded_name = ABBREVIATION_MAP.get(entity_name.upper(), entity_name)
    primary_api = ENTITY_TYPE_TO_API_MAP.get(entity_type)

    if not primary_api:
        fallback_id = generate_fallback_id(entity_name, entity_type)
        return {"ontology_id": fallback_id, "standard_name": entity_name.title()}

    # 2. Create context-rich clinical sentence for the API
    # AWS Comprehend Medical works best with clinical text, not isolated terms
    # Preserve entity type context with appropriate sentence structure
    
    # Map entity types to clinical sentence templates
    # Covers all 19+ node types from COMPREHENSIVE_SCHEMA
    entity_type_templates = {
        # Clinical Concepts (5 types)
        "Disease": f"Patient diagnosed with {expanded_name}.",
        "Pathological_Finding": f"Patient presents with {expanded_name}.",
        "Symptom": f"Patient reports {expanded_name}.",
        "Clinical_Finding": f"Examination reveals {expanded_name}.",
        "Side_Effect": f"Patient experienced {expanded_name} as adverse reaction.",
        
        # Interventions (4 types)
        "Medication": f"Patient prescribed {expanded_name}.",
        "Treatment": f"Patient received {expanded_name} treatment.",
        "Diagnostic_Procedure": f"Patient underwent {expanded_name}.",
        "Medical_Device": f"Procedure uses {expanded_name} device.",
        
        # Biological & Genetic Concepts (6 types)
        "Anatomy": f"Examination of patient's {expanded_name}.",
        "Pathogen": f"Patient infected with {expanded_name}.",
        "Gene": f"Genetic testing for {expanded_name} gene.",
        "Protein": f"Analysis of {expanded_name} protein levels.",
        "Cell_Type": f"Analysis of {expanded_name} cells.",
        "Genetic_Disorder": f"Patient has {expanded_name} genetic condition.",
        "Biological_Process": f"Evaluation of {expanded_name} process.",
        
        # Contextual & Epidemiological Concepts (4 types)
        "Clinical_Study": f"Research study on {expanded_name}.",
        "Age_Group": f"Patient population: {expanded_name}.",
        "Lifestyle_Factor": f"Patient lifestyle includes {expanded_name}.",
        "Environmental_Factor": f"Patient exposed to {expanded_name}.",
    }
    
    # Use template if available, otherwise fall back to generic format
    text_for_api = entity_type_templates.get(
        entity_type, 
        f"Clinical assessment: {expanded_name}."
    )

    # 3. Define API calling function (with retry logic)
    def try_api(api_name: str):
        """Helper function to call either SNOMED or RxNorm API with retry."""
        @retry_on_failure(max_retries=2, initial_delay=1.0, backoff_factor=2.0)
        def call_aws_api():
            if api_name == "snomed":
                response = aws_client.infer_snomedct(Text=text_for_api)
                concept_key = 'SNOMEDCTConcepts'
                api_prefix = 'SNOMEDCT'
            elif api_name == "rxnorm":
                response = aws_client.infer_rx_norm(Text=text_for_api)
                concept_key = 'RxNormConcepts'
                api_prefix = 'RXNORM'
            else:
                return None, None, None
            
            return response.get('Entities', []), concept_key, api_prefix
        
        try:
            entities, concept_key, api_prefix = call_aws_api()
            
            if not entities:
                return None

            # Find the best concept from the response
            best_concept = None
            highest_score = 0.0

            for entity in entities:
                for concept in entity.get(concept_key, []):
                    if concept['Score'] > highest_score:
                        highest_score = concept['Score']
                        best_concept = concept

            if best_concept and highest_score >= MIN_CONFIDENCE_SCORE:
                return {
                    "ontology_id": f"{api_prefix}:{best_concept['Code']}",
                    "standard_name": clean_description(best_concept['Description']),
                    "_confidence": highest_score,  # Internal tracking (underscore prefix)
                    "_api_used": api_name          # Internal tracking (underscore prefix)
                }
            elif best_concept:
                # AWS found something but confidence too low
                print(f"  - ⚠️  AWS found '{entity_name}' but confidence too low: {highest_score:.2f} < {MIN_CONFIDENCE_SCORE}")
            return None

        except Exception as e:
            print(f"  - AWS {api_name.upper()} API Error for '{entity_name}' (all retries failed): {e}")
            return None

    try:
        # 4. Try primary API first
        result = try_api(primary_api)
        if result:
            print(f"  - ✅ {entity_name} → {result['ontology_id']} (primary {result['_api_used']}, conf: {result['_confidence']:.2f})")
            return result

        # 5. Try secondary API as fallback
        secondary_api = "rxnorm" if primary_api == "snomed" else "snomed"
        result = try_api(secondary_api)
        if result:
            print(f"  - ✅ {entity_name} → {result['ontology_id']} (fallback {result['_api_used']}, conf: {result['_confidence']:.2f})")
            return result

        # 6. No confident match found in either API - use fallback ID
        fallback_id = generate_fallback_id(entity_name, entity_type)
        print(f"  - ⚠️  {entity_name} → {fallback_id} (no AWS match)")
        return {"ontology_id": fallback_id, "standard_name": entity_name.title()}

    except Exception as e:
        print(f"  - ❌ Unexpected error for '{entity_name}': {e}")
        fallback_id = generate_fallback_id(entity_name, entity_type)
        return {"ontology_id": fallback_id, "standard_name": entity_name.title()}
     
# --- 5b. Synonym Acquisition ---

def get_synonyms_from_text_search(entity_name: str, entity_type: str, umls_cursor, max_results: int = 15) -> list:
    """
    Direct text-based search in UMLS for entities that couldn't be standardized.
    Uses fuzzy matching with confidence scoring.
    """
    if not umls_cursor or not entity_name.strip():
        return []
    
    try:
        # Clean the entity name for searching
        search_term = entity_name.strip()
        
        # Strategy 1: Exact match (highest priority)
        umls_cursor.execute("""
            SELECT DISTINCT CUI, STR, SAB, TTY,
                   CASE WHEN SAB = 'SNOMEDCT_US' THEN 1 
                        WHEN SAB = 'RXNORM' THEN 2
                        WHEN SAB = 'MSH' THEN 3
                        ELSE 4 END as sab_priority
            FROM mrconso 
            WHERE UPPER(STR) = UPPER(%s)
              AND LAT = 'ENG' 
              AND SUPPRESS = 'N'
            ORDER BY sab_priority
            LIMIT 3
        """, (search_term,))
        
        exact_matches = umls_cursor.fetchall()
        if exact_matches:
            # Found exact match - get all synonyms for the best CUI
            best_cui = exact_matches[0][0]  # Take the first (highest priority) match
            
            umls_cursor.execute("""
                SELECT DISTINCT STR, TTY, LENGTH(STR) as str_length,
                       CASE WHEN TTY = 'PT' THEN 1   -- Preferred terms first
                            WHEN TTY = 'SY' THEN 2   -- Synonyms  
                            WHEN TTY = 'AB' THEN 3   -- Abbreviations
                            ELSE 4 END as tty_priority
                FROM mrconso 
                WHERE CUI = %s 
                  AND LAT = 'ENG' 
                  AND SUPPRESS = 'N'
                ORDER BY tty_priority, str_length
                LIMIT %s
            """, (best_cui, max_results))
            
            synonyms = [row[0] for row in umls_cursor.fetchall()]
            if synonyms:
                return synonyms
        
        # Strategy 2: Partial match (if no exact match)
        partial_search = f"%{search_term}%"
        umls_cursor.execute("""
            SELECT DISTINCT CUI, STR, SAB, LENGTH(STR) as str_length,
                   CASE WHEN SAB = 'SNOMEDCT_US' THEN 1 
                        WHEN SAB = 'RXNORM' THEN 2
                        WHEN SAB = 'MSH' THEN 3
                        ELSE 4 END as sab_priority
            FROM mrconso 
            WHERE UPPER(STR) LIKE UPPER(%s)
              AND LAT = 'ENG' 
              AND SUPPRESS = 'N'
              AND LENGTH(STR) - LENGTH(%s) <= 10  -- Avoid very long partial matches
            ORDER BY sab_priority, str_length
            LIMIT 5
        """, (partial_search, search_term))
        
        partial_matches = umls_cursor.fetchall()
        if partial_matches:
            # Get synonyms for the best partial match
            best_cui = partial_matches[0][0]
            
            umls_cursor.execute("""
                SELECT DISTINCT STR, LENGTH(STR) as str_length
                FROM mrconso 
                WHERE CUI = %s 
                  AND LAT = 'ENG' 
                  AND SUPPRESS = 'N'
                ORDER BY str_length
                LIMIT %s
            """, (best_cui, max_results))
            
            synonyms = [row[0] for row in umls_cursor.fetchall()]
            if synonyms:
                return synonyms
        
        # Strategy 3: Word-based search (if still no matches)
        # Split entity name into words and search for concepts containing all words
        words = [w.strip() for w in search_term.split() if len(w.strip()) > 2]
        if len(words) >= 2:  # Only if we have multiple meaningful words
            word_conditions = " AND ".join([f"UPPER(STR) LIKE UPPER('%{word}%')" for word in words])
            
            umls_cursor.execute(f"""
                SELECT DISTINCT CUI, STR, SAB, LENGTH(STR) as str_length,
                       CASE WHEN SAB = 'SNOMEDCT_US' THEN 1 
                            WHEN SAB = 'RXNORM' THEN 2
                            WHEN SAB = 'MSH' THEN 3
                            ELSE 4 END as sab_priority
                FROM mrconso 
                WHERE {word_conditions}
                  AND LAT = 'ENG' 
                  AND SUPPRESS = 'N'
                ORDER BY sab_priority, str_length
                LIMIT 3
            """)
            
            word_matches = umls_cursor.fetchall()
            if word_matches:
                best_cui = word_matches[0][0]
                
                umls_cursor.execute("""
                    SELECT DISTINCT STR, LENGTH(STR) as str_length
                    FROM mrconso 
                    WHERE CUI = %s 
                      AND LAT = 'ENG' 
                      AND SUPPRESS = 'N'
                    ORDER BY str_length
                    LIMIT %s
                """, (best_cui, max_results))
                
                synonyms = [row[0] for row in umls_cursor.fetchall()]
                if synonyms:
                    return synonyms
        
        # No matches found
        return []
        
    except Exception as e:
        print(f"Error in text-based synonym search for '{entity_name}': {e}")
        # Rollback the transaction to recover from error
        try:
            umls_cursor.connection.rollback()
        except:
            pass
        return []

def batch_get_synonyms(entities_data: list, umls_cursor) -> dict:
    """
    Batch synonym lookup for multiple entities with minimal DB queries.
    
    Args:
        entities_data: List of dicts with {ontology_id, entity_name, entity_type}
        umls_cursor: PostgreSQL cursor
    
    Returns:
        Dict mapping ontology_id -> list of synonyms
    """
    if not umls_cursor or not entities_data:
        return {}
    
    results = {}
    
    try:
        # Group entities by type
        snomed_entities = []
        rxnorm_entities = []
        biograph_entities = []
        other_entities = []
        
        for entity_data in entities_data:
            ont_id = entity_data['ontology_id']
            if ont_id.startswith("SNOMEDCT:"):
                snomed_entities.append(entity_data)
            elif ont_id.startswith("RXNORM:"):
                rxnorm_entities.append(entity_data)
            elif ont_id.startswith("BIOGRAPH:"):
                biograph_entities.append(entity_data)
            else:
                other_entities.append(entity_data)
        
        # Batch process SNOMED entities
        if snomed_entities:
            snomed_codes = [e['ontology_id'].replace("SNOMEDCT:", "") for e in snomed_entities]
            
            # Single query to get all CUIs
            umls_cursor.execute("""
                SELECT DISTINCT CODE, CUI 
                FROM mrconso 
                WHERE CODE = ANY(%s) AND SAB = 'SNOMEDCT_US'
            """, (snomed_codes,))
            
            code_to_cui = {row[0]: row[1] for row in umls_cursor.fetchall()}
            
            if code_to_cui:
                # Single query to get all synonyms for all CUIs
                cuis = list(code_to_cui.values())
                umls_cursor.execute("""
                    SELECT DISTINCT CUI, STR, TTY, LENGTH(STR) as str_length,
                           CASE WHEN TTY = 'PT' THEN 1 ELSE 2 END as tty_priority
                    FROM mrconso 
                    WHERE CUI = ANY(%s)
                      AND LAT = 'ENG' 
                      AND SUPPRESS = 'N'
                    ORDER BY CUI, tty_priority, str_length
                """, (cuis,))
                
                # Group synonyms by CUI
                cui_to_synonyms = {}
                for cui, str_val, tty, str_length, tty_priority in umls_cursor.fetchall():
                    if cui not in cui_to_synonyms:
                        cui_to_synonyms[cui] = []
                    if len(cui_to_synonyms[cui]) < 20:  # Limit to 20 per entity
                        cui_to_synonyms[cui].append(str_val)
                
                # Map back to ontology IDs
                for entity_data in snomed_entities:
                    code = entity_data['ontology_id'].replace("SNOMEDCT:", "")
                    cui = code_to_cui.get(code)
                    if cui and cui in cui_to_synonyms:
                        results[entity_data['ontology_id']] = cui_to_synonyms[cui]
                        print(f"    📖 Found {len(cui_to_synonyms[cui])} synonyms via SNOMED CUI {cui}")
                    else:
                        results[entity_data['ontology_id']] = []
        
        # Batch process RxNorm entities
        if rxnorm_entities:
            rxnorm_codes = [e['ontology_id'].replace("RXNORM:", "") for e in rxnorm_entities]
            
            # Single query to get all CUIs
            umls_cursor.execute("""
                SELECT DISTINCT CODE, CUI 
                FROM mrconso 
                WHERE CODE = ANY(%s) AND SAB = 'RXNORM'
            """, (rxnorm_codes,))
            
            code_to_cui = {row[0]: row[1] for row in umls_cursor.fetchall()}
            
            if code_to_cui:
                # Single query to get all synonyms for all CUIs
                cuis = list(code_to_cui.values())
                umls_cursor.execute("""
                    SELECT DISTINCT CUI, STR, TTY, LENGTH(STR) as str_length,
                           CASE WHEN TTY = 'PT' THEN 1 ELSE 2 END as tty_priority
                    FROM mrconso 
                    WHERE CUI = ANY(%s)
                      AND LAT = 'ENG' 
                      AND SUPPRESS = 'N'
                    ORDER BY CUI, tty_priority, str_length
                """, (cuis,))
                
                # Group synonyms by CUI
                cui_to_synonyms = {}
                for cui, str_val, tty, str_length, tty_priority in umls_cursor.fetchall():
                    if cui not in cui_to_synonyms:
                        cui_to_synonyms[cui] = []
                    if len(cui_to_synonyms[cui]) < 20:
                        cui_to_synonyms[cui].append(str_val)
                
                # Map back to ontology IDs
                for entity_data in rxnorm_entities:
                    code = entity_data['ontology_id'].replace("RXNORM:", "")
                    cui = code_to_cui.get(code)
                    if cui and cui in cui_to_synonyms:
                        results[entity_data['ontology_id']] = cui_to_synonyms[cui]
                        print(f"    📖 Found {len(cui_to_synonyms[cui])} synonyms via RxNorm CUI {cui}")
                    else:
                        results[entity_data['ontology_id']] = []
        
        # Process BIOGRAPH entities (skip slow text searches - these aren't in medical ontologies anyway)
        for entity_data in biograph_entities:
            # Skip UMLS text search for entities not in SNOMED/RxNorm
            # These are typically agricultural/veterinary terms not in medical databases
            results[entity_data['ontology_id']] = []
            # Removed slow text search: get_synonyms_from_text_search()
        
        # Process other entities
        for entity_data in other_entities:
            # Try direct CUI lookup
            umls_cursor.execute("""
                SELECT DISTINCT STR 
                FROM mrconso 
                WHERE CUI = %s 
                  AND LAT = 'ENG' 
                  AND SUPPRESS = 'N'
                LIMIT 20
            """, (entity_data['ontology_id'],))
            
            synonyms = [row[0] for row in umls_cursor.fetchall()]
            
            # Fallback to text search if no CUI match
            if not synonyms and entity_data.get('entity_name'):
                synonyms = get_synonyms_from_text_search(
                    entity_data['entity_name'],
                    entity_data.get('entity_type', ''),
                    umls_cursor
                )
            
            results[entity_data['ontology_id']] = synonyms
    
    except Exception as e:
        print(f"  - ⚠️  Error in batch synonym lookup: {e}")
        try:
            umls_cursor.connection.rollback()
        except:
            pass
    
    return results


def get_synonyms(ontology_id: str, umls_cursor, original_entity_name: str = None, entity_type: str = None) -> list:
    """
    HYBRID synonym lookup function with comprehensive coverage:
    1. Standardized IDs (SNOMEDCT/RXNORM) → Precise ontology-based lookup
    2. Fallback IDs (BIOGRAPH) → Direct text-based search in UMLS  
    3. Unknown formats → Try direct CUI lookup first, then text search
    """
    if not umls_cursor:
        return []
    
    try:
        synonyms = []
        
        # STRATEGY 1: Precise Ontology-based Lookup (for standardized entities)
        if ontology_id.startswith("SNOMEDCT:"):
            # Extract SNOMED code and find synonyms via CUI
            snomed_code = ontology_id.replace("SNOMEDCT:", "")
            
            umls_cursor.execute("""
                SELECT DISTINCT CUI 
                FROM mrconso 
                WHERE CODE = %s AND SAB = 'SNOMEDCT_US'
                LIMIT 1
            """, (snomed_code,))
            
            result = umls_cursor.fetchone()
            if result:
                cui = result[0]
                
                umls_cursor.execute("""
                    SELECT DISTINCT STR, TTY, LENGTH(STR) as str_length,
                           CASE WHEN TTY = 'PT' THEN 1 ELSE 2 END as tty_priority
                    FROM mrconso 
                    WHERE CUI = %s 
                      AND LAT = 'ENG' 
                      AND SUPPRESS = 'N'
                    ORDER BY tty_priority, str_length
                    LIMIT 20
                """, (cui,))
                
                synonyms = [row[0] for row in umls_cursor.fetchall()]
                if synonyms:
                    print(f"    📖 Found {len(synonyms)} synonyms via SNOMED CUI {cui}")
        
        elif ontology_id.startswith("RXNORM:"):
            # Extract RxNorm code and find synonyms via CUI
            rxnorm_code = ontology_id.replace("RXNORM:", "")
            
            umls_cursor.execute("""
                SELECT DISTINCT CUI 
                FROM mrconso 
                WHERE CODE = %s AND SAB = 'RXNORM'
                LIMIT 1
            """, (rxnorm_code,))
            
            result = umls_cursor.fetchone()
            if result:
                cui = result[0]
                
                umls_cursor.execute("""
                    SELECT DISTINCT STR, TTY, LENGTH(STR) as str_length,
                           CASE WHEN TTY = 'PT' THEN 1 ELSE 2 END as tty_priority
                    FROM mrconso 
                    WHERE CUI = %s 
                      AND LAT = 'ENG' 
                      AND SUPPRESS = 'N'
                    ORDER BY tty_priority, str_length
                    LIMIT 20
                """, (cui,))
                
                synonyms = [row[0] for row in umls_cursor.fetchall()]
                if synonyms:
                    print(f"    📖 Found {len(synonyms)} synonyms via RxNorm CUI {cui}")
        
        # STRATEGY 2: Text-based Search (for fallback entities)
        elif ontology_id.startswith("BIOGRAPH:"):
            # Use direct text search for entities that couldn't be standardized
            if original_entity_name:
                synonyms = get_synonyms_from_text_search(original_entity_name, entity_type or "", umls_cursor)
                if synonyms:
                    print(f"    🔍 Found {len(synonyms)} synonyms via text search for '{original_entity_name}'")
                else:
                    print(f"    ❌ No UMLS synonyms found for '{original_entity_name}'")
        
        # STRATEGY 3: Direct CUI Lookup (for unknown formats)
        else:
            # Try direct CUI lookup first
            umls_cursor.execute("""
                SELECT DISTINCT STR, TTY, LENGTH(STR) as str_length,
                       CASE WHEN TTY = 'PT' THEN 1 ELSE 2 END as tty_priority
                FROM mrconso 
                WHERE CUI = %s 
                  AND LAT = 'ENG' 
                  AND SUPPRESS = 'N'
                ORDER BY tty_priority, str_length
                LIMIT 20
            """, (ontology_id,))
            
            synonyms = [row[0] for row in umls_cursor.fetchall()]
            
            # If direct CUI lookup failed and we have original text, try text search
            if not synonyms and original_entity_name:
                synonyms = get_synonyms_from_text_search(original_entity_name, entity_type or "", umls_cursor)
                if synonyms:
                    print(f"    🔍 Found {len(synonyms)} synonyms via fallback text search")
        
        return synonyms
        
    except Exception as e:
        print(f"Error getting synonyms for {ontology_id}: {e}")
        # Rollback the transaction to recover from error
        try:
            umls_cursor.connection.rollback()
        except:
            pass
        return []

# --- 5c. Vector Embedding ---
def get_embedding(text: str, embedding_model) -> list:
    """
    Generates a vector embedding for a given text.
    """
    # TODO: Ensure the sentence-transformer model is loaded correctly.
    # This function uses the loaded model.
    try:
        return embedding_model.encode(text)
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return []

# --- 5d. Main Orchestration Function ---
def process_text_chunk(text_chunk: str, document_context: dict, llm, aws_client, umls_cursor, embedding_model) -> dict:
    """
    Orchestrates the entire enrichment pipeline for a single chunk of text.
    
    Args:
        text_chunk: The text content to process
        document_context: Document metadata including species and source information
        llm: Initialized LLM instance
        aws_client: AWS Comprehend Medical client
        umls_cursor: PostgreSQL cursor for UMLS database
        embedding_model: Sentence transformer model for embeddings
        
    Returns:
        dict: Processed nodes and relationships with species and source metadata
    """
    print("  - Sending chunk to LLM for initial extraction")

    # 1. Initial Extraction with Live LLM (with retries for transient failures)
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        node_types=', '.join(COMPREHENSIVE_SCHEMA['node_types']),
        relationship_types=', '.join(COMPREHENSIVE_SCHEMA['relationship_types']),
        text_chunk=text_chunk,
        # Document context for species handling
        source_title=document_context.get('title', 'Unknown'),
        source_journal=document_context.get('journal', 'Unknown'),
        source_year=document_context.get('publication_year', 'Unknown'),
        document_species=document_context.get('primary_species', 'not specified'),
        study_type=document_context.get('study_type', 'other')
    )
    
    @retry_on_failure(max_retries=3, initial_delay=2.0, backoff_factor=2.0)
    def call_llm_with_retry():
        response = llm.complete(prompt)
        return response.text
    
    try:
        llm_output_text = call_llm_with_retry()
    except Exception as e:
        print(f"  - LLM API Error (all retries failed): {e}")
        return {"nodes": [], "relationships": []} # Return empty on error
    
    # print("LLM response: ", llm_output_text)

    # 2. Parse the LLM's JSON response
    try:
        # The LLM might wrap the JSON in markdown backticks, so we find it.
        match = re.search(r"```json\s*(\{.*\})\s*```", llm_output_text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            json_str = llm_output_text

        raw_data = json.loads(json_str)
        entities = raw_data.get("entities", [])
        relationships = raw_data.get("relationships", [])
        print(f"  - LLM extracted {len(entities)} entities and {len(relationships)} relationships.")
    except json.JSONDecodeError as e:
        # Try to recover from truncated JSON by closing brackets
        print(f"  - WARNING: JSON parse error, attempting recovery...")
        try:
            # Count brackets to see if JSON is incomplete
            open_braces = json_str.count('{')
            close_braces = json_str.count('}')
            open_brackets = json_str.count('[')
            close_brackets = json_str.count(']')
            
            # Try to close incomplete JSON
            fixed_json = json_str
            if open_brackets > close_brackets:
                fixed_json += ']' * (open_brackets - close_brackets)
            if open_braces > close_braces:
                fixed_json += '}' * (open_braces - close_braces)
            
            raw_data = json.loads(fixed_json)
            entities = raw_data.get("entities", [])
            relationships = raw_data.get("relationships", [])
            print(f"  - ✅ Recovered! Extracted {len(entities)} entities and {len(relationships)} relationships.")
        except:
            print("  - ERROR: LLM did not return a valid JSON object (recovery failed).")
            print(f"  - Parse error: {e}")
            if len(llm_output_text) > 500:
                print(f"  - Output preview (first 500 chars):\n{llm_output_text[:500]}...")
                print(f"  - Output preview (last 500 chars):\n...{llm_output_text[-500:]}")
            else:
                print(f"  - Raw LLM Output:\n{llm_output_text}")
            return {"nodes": [], "relationships": []}


    # 3. Enrich Entities
    enriched_nodes = {}
    entity_to_id_map = {}
    if entities:
        print(f"  - Standardizing and enriching {len(entities)} entities...")
        
        # Apply species logic to all entities BEFORE standardization
        entities_with_species = []
        for entity in entities:
            entity = apply_species_logic_to_node(entity, document_context)
            entities_with_species.append(entity)
        
        # STANDARDIZE: Parallel AWS Comprehend calls (4 workers for 4x speedup)
        print(f"  - Calling AWS Comprehend for {len(entities_with_species)} entities (parallel)...")
        batch_standard_results = batch_standardize_entities(entities_with_species, aws_client, max_workers=4)
        print(f"  - AWS standardization complete!")
        
        # Prepare entities for batch synonym lookup
        entities_for_synonym_lookup = []
        entity_ontology_map = {}  # Map entity_key to final ontology_id
        
        # First pass: compute ontology IDs and print results
        for entity in entities_with_species:
            entity_key = (entity['entity_name'], entity['entity_type'])

            # Get pre-computed standardization result from batch
            standard_info = batch_standard_results.get(entity_key)
            if not standard_info:
                standard_info = {
                    'ontology_id': generate_fallback_id(entity['entity_name'], entity['entity_type']),
                    'standard_name': entity['entity_name'].title()
                }
            
            ontology_id = standard_info['ontology_id']
            
            # Print result for this entity
            if standard_info.get('_api_used'):
                print(f"  - ✅ {entity['entity_name']} → {ontology_id} ({standard_info['_api_used']}, conf: {standard_info.get('_confidence', 0):.2f})")
            else:
                print(f"  - ⚠️  {entity['entity_name']} → {ontology_id} (no AWS match)")
            
            # For species-specific nodes, include species in the ontology_id
            if entity.get('_needs_species_suffix') and entity.get('species'):
                species_suffix = entity['species'].replace(' ', '_').replace('(', '').replace(')', '')
                if species_suffix not in ontology_id:
                    ontology_id = f"{ontology_id}_{species_suffix}"
            
            entity['_final_ontology_id'] = ontology_id
            entity['_standard_info'] = standard_info
            entity_ontology_map[entity_key] = ontology_id
            
            # Collect unique entities for synonym lookup
            if ontology_id not in enriched_nodes:
                entities_for_synonym_lookup.append({
                    'ontology_id': ontology_id,
                    'entity_name': entity['entity_name'],
                    'entity_type': entity['entity_type']
                })
        
        # BATCH SYNONYM LOOKUP: Single call for all entities
        print(f"  - Batch calling UMLS for synonyms...")
        batch_synonyms = batch_get_synonyms(entities_for_synonym_lookup, umls_cursor)
        
        # Second pass: build nodes with pre-fetched synonyms
        for entity in entities_with_species:
            entity_key = (entity['entity_name'], entity['entity_type'])
            ontology_id = entity['_final_ontology_id']
            standard_info = entity['_standard_info']

            if ontology_id not in enriched_nodes:
                # Get pre-fetched synonyms
                synonyms = batch_synonyms.get(ontology_id, [])
                
                summary = f"Concept: {standard_info['standard_name']}. Description: {entity['entity_description']}"
                embedding = get_embedding(summary, embedding_model)

                # Combine original entity name with found synonyms (deduplicated)
                all_synonyms = list(set([entity['entity_name']] + synonyms))

                # Build node with species and source metadata
                node_data = {
                    "ontology_id": ontology_id,
                    "label": entity['entity_type'],
                    "standard_name": standard_info['standard_name'],
                    "synonyms": all_synonyms,
                    "description": entity['entity_description'],
                    "embedding": embedding,
                    "source_id": document_context['source_id']
                }
                
                # Add species for species-specific node types
                if entity.get('species'):
                    node_data["species"] = entity['species']
                    if entity.get('species_confidence'):
                        node_data["species_confidence"] = entity['species_confidence']
                
                # Clean up internal flags
                entity.pop('_needs_species_suffix', None)
                entity.pop('_final_ontology_id', None)
                entity.pop('_standard_info', None)
                
                enriched_nodes[ontology_id] = node_data
            entity_to_id_map[entity_key] = ontology_id

    # 4. Map Relationships using the generated IDs
    enriched_relationships = []
    if relationships:
        print(f"  - Mapping {len(relationships)} relationships...")
        for rel in relationships:
            # Apply species logic to relationship
            rel = apply_species_logic_to_relationship(rel, document_context)
            
            source_key = (rel['source_entity_name'], rel['source_entity_type'])
            target_key = (rel['target_entity_name'], rel['target_entity_type'])

            source_id = entity_to_id_map.get(source_key)
            target_id = entity_to_id_map.get(target_key)

            if source_id and target_id:
                enriched_relationships.append({
                    "source_id": source_id,
                    "target_id": target_id,
                    "label": rel['relation_type'],
                    "description": rel['relationship_description'],
                    "species": rel['species'],
                    "species_confidence": rel['species_confidence'],
                    "source_id_ref": document_context['source_id']  # Reference to Source node
                })

    return {"nodes": list(enriched_nodes.values()), "relationships": enriched_relationships}

print("Enrichment pipeline functions defined.")

# =============================================================================
# Step 6: REFINED DATABASE LOADING FUNCTIONS
# =============================================================================

# =============================================================================
# REFINED DATABASE LOADING FUNCTIONS (v1.1 - Syntax Fix)
# =============================================================================

def create_source_node(driver, document_context):
    """
    Create or update a Source node in Neo4j with document metadata.
    
    Args:
        driver: Neo4j driver instance
        document_context: Dictionary with document metadata
        
    Returns:
        None
    """
    query = """
    MERGE (s:Source {source_id: $source_id})
    SET s.source_type = $source_type,
        s.source_platform = $source_platform,
        s.title = $title,
        s.authors = $authors,
        s.journal = $journal,
        s.publication_year = $publication_year,
        s.doi = $doi,
        s.primary_species = $primary_species,
        s.species_confidence = $species_confidence,
        s.species_evidence = $species_evidence,
        s.study_type = $study_type,
        s.processing_date = $processing_date,
        s.document_path = $document_path
    RETURN s
    """
    
    def _create_source(tx):
        result = tx.run(query, **document_context)
        return result.single()
    
    with driver.session() as session:
        result = session.execute_write(_create_source)
        if result:
            print(f"  ✅ Source node created/updated: {document_context['source_id']}")
        else:
            print(f"  ⚠️  Warning: Source node creation returned no result")


def load_nodes_to_neo4j(tx, nodes):
    """
    Loads a batch of nodes into Neo4j with species and source metadata.
    Creates EXTRACTED_FROM relationships to Source nodes.
    """
    # First, create/update entity nodes
    node_query = """
    UNWIND $nodes as node_data
    MERGE (n {ontology_id: node_data.ontology_id})
    SET n.standard_name = node_data.standard_name,
        n.synonyms = node_data.synonyms,
        n.description = node_data.description,
        n.embedding = node_data.embedding
    // Conditionally set species fields (only for species-specific node types)
    FOREACH (ignoreMe IN CASE WHEN node_data.species IS NOT NULL THEN [1] ELSE [] END |
        SET n.species = node_data.species,
            n.species_confidence = node_data.species_confidence
    )
    WITH n, node_data.label AS label, node_data.source_id AS source_id
    CALL apoc.create.addLabels(n, [label]) YIELD node
    // Create EXTRACTED_FROM relationship to Source node (only if Source exists)
    WITH node, source_id
    OPTIONAL MATCH (s:Source {source_id: source_id})
    FOREACH (ignoreMe IN CASE WHEN s IS NOT NULL THEN [1] ELSE [] END |
        MERGE (node)-[r:EXTRACTED_FROM]->(s)
        SET r.extraction_date = datetime()
    )
    RETURN count(node) AS nodes_created, count(s) AS sources_found
    """
    result = tx.run(node_query, nodes=nodes)
    summary = result.single()
    if summary and summary['sources_found'] == 0:
        print(f"  ⚠️  Warning: Source node not found for some entities. EXTRACTED_FROM relationships not created.")

def load_relationships_to_neo4j(tx, relationships):
    """
    Loads a batch of relationships into Neo4j with species and source metadata.
    """
    query = """
    UNWIND $relationships as rel_data
    MATCH (source {ontology_id: rel_data.source_id})
    MATCH (target {ontology_id: rel_data.target_id})
    CALL apoc.merge.relationship(source, rel_data.label, {}, {
        evidence_text: rel_data.description,
        species: rel_data.species,
        species_confidence: rel_data.species_confidence,
        source_id: rel_data.source_id_ref
    }, target) YIELD rel
    RETURN count(rel)
    """
    tx.run(query, relationships=relationships)
    
print("Neo4j loading functions initialised.")


# =============================================================================
# STEP 7: BATCH PREPARATION FUNCTIONS
# These functions prepare JSONL files for batch processing
# =============================================================================

def prepare_batch_jsonl(
    source_file_path: str, 
    output_jsonl_path: str = None,
    chunk_size: int = 512,
    chunk_overlap: int = 20,
    max_chunks_per_file: int = None
) -> dict:
    """
    Prepares a JSONL file for batch processing from a source document.
    
    Args:
        source_file_path: Path to the source document to process
        output_jsonl_path: Path for the output JSONL file (defaults to source_name_batch.jsonl)
        chunk_size: Size of text chunks in tokens (default: 512)
        chunk_overlap: Overlap between chunks in tokens (default: 20)
        max_chunks_per_file: Maximum chunks per JSONL file (None = no limit)
    
    Returns:
        dict: Statistics about the batch preparation
            - total_chunks: Total number of chunks created
            - total_tokens_estimate: Estimated total tokens (chunks * avg tokens)
            - output_files: List of output JSONL files created
            - chunks_per_file: List of chunk counts per file
    """
    import json
    from pathlib import Path
    from llama_index.core import Document
    from llama_index.core.node_parser import SentenceSplitter
    
    print(f"\n--- Preparing Batch JSONL from '{source_file_path}' ---")
    
    # Read the source document
    try:
        with open(source_file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        print(f"  - Successfully read source file ({len(text)} characters)")
    except FileNotFoundError:
        print(f"  - ERROR: Source file not found at '{source_file_path}'")
        return {"error": "File not found"}
    except Exception as e:
        print(f"  - ERROR reading file: {e}")
        return {"error": str(e)}
    
    # Create document and split into chunks
    documents = [Document(text=text)]
    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    text_nodes = splitter.get_nodes_from_documents(documents)
    total_chunks = len(text_nodes)
    print(f"  - Split document into {total_chunks} chunks")
    
    # Prepare the prompt template with schema - we need to be careful with the formatting
    # First, let's prepare the base template with schema but without the text chunk
    base_prompt = EXTRACTION_PROMPT_TEMPLATE.replace('{text_chunk}', '<<<TEXT_CHUNK_PLACEHOLDER>>>')
    formatted_base_prompt = base_prompt.format(
        node_types=', '.join(COMPREHENSIVE_SCHEMA['node_types']),
        relationship_types=', '.join(COMPREHENSIVE_SCHEMA['relationship_types'])
    )
    
    # Determine output file path(s)
    if output_jsonl_path is None:
        source_path = Path(source_file_path)
        output_jsonl_path = source_path.parent / f"{source_path.stem}_batch.jsonl"
    else:
        output_jsonl_path = Path(output_jsonl_path)
    
    # Statistics tracking
    stats = {
        "total_chunks": total_chunks,
        "total_tokens_estimate": total_chunks * chunk_size,  # Rough estimate
        "output_files": [],
        "chunks_per_file": []
    }
    
    # Process chunks and write to JSONL
    if max_chunks_per_file is None:
        # Single file output
        print(f"  - Writing all {total_chunks} chunks to single JSONL file...")
        
        try:
            with open(output_jsonl_path, 'w', encoding='utf-8') as f:
                for i, node in enumerate(text_nodes):
                    chunk_text = node.get_content()
                    
                    # Format the prompt with this specific chunk
                    prompt = formatted_base_prompt.replace('<<<TEXT_CHUNK_PLACEHOLDER>>>', chunk_text)
                    
                    # Create the batch request object
                    # Format follows Bedrock batch requirements
                    batch_request = {
                        "custom_id": f"chunk_{i}",
                        "method": "POST",
                        "url": "/model/invoke",
                        "body": {
                            "prompt": prompt,
                            "max_tokens": 4096,
                            "temperature": 0.1
                        }
                    }
                    
                    # Write as a single line of JSON
                    f.write(json.dumps(batch_request) + '\n')
                    
                    if (i + 1) % 100 == 0:
                        print(f"    - Processed {i + 1}/{total_chunks} chunks...")
            
            stats["output_files"].append(str(output_jsonl_path))
            stats["chunks_per_file"].append(total_chunks)
            print(f"  - Successfully wrote {total_chunks} prompts to: {output_jsonl_path}")
            
        except Exception as e:
            print(f"  - ERROR writing JSONL file: {e}")
            stats["error"] = str(e)
    
    else:
        # Multiple file output (for very large documents)
        print(f"  - Splitting into multiple files (max {max_chunks_per_file} chunks each)...")
        
        file_index = 0
        for start_idx in range(0, total_chunks, max_chunks_per_file):
            end_idx = min(start_idx + max_chunks_per_file, total_chunks)
            chunk_count = end_idx - start_idx
            
            # Create filename for this batch
            output_path = output_jsonl_path.parent / f"{output_jsonl_path.stem}_part{file_index}{output_jsonl_path.suffix}"
            
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    for i in range(start_idx, end_idx):
                        node = text_nodes[i]
                        chunk_text = node.get_content()
                        
                        # Format the prompt
                        prompt = formatted_base_prompt.replace('<<<TEXT_CHUNK_PLACEHOLDER>>>', chunk_text)
                        
                        # Create batch request
                        batch_request = {
                            "custom_id": f"chunk_{i}",
                            "method": "POST", 
                            "url": "/model/invoke",
                            "body": {
                                "prompt": prompt,
                                "max_tokens": 4096,
                                "temperature": 0.1
                            }
                        }
                        
                        f.write(json.dumps(batch_request) + '\n')
                
                stats["output_files"].append(str(output_path))
                stats["chunks_per_file"].append(chunk_count)
                print(f"    - Wrote {chunk_count} chunks to: {output_path}")
                file_index += 1
                
            except Exception as e:
                print(f"  - ERROR writing JSONL file part {file_index}: {e}")
                stats["error"] = str(e)
                break
    
    # Print summary statistics
    print("\n--- Batch Preparation Summary ---")
    print(f"  Total chunks: {stats['total_chunks']}")
    print(f"  Estimated tokens: ~{stats['total_tokens_estimate']:,}")
    print(f"  Output files: {len(stats['output_files'])}")
    
    if len(stats['output_files']) > 1:
        for i, (file, count) in enumerate(zip(stats['output_files'], stats['chunks_per_file'])):
            print(f"    - Part {i}: {count} chunks -> {file}")
    
    return stats


print("Batch preparation functions added.")