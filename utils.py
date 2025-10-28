import os
import json
import re
import hashlib
from getpass import getpass

# Core libraries
import boto3  # For AWS Comprehend Medical
import psycopg2  # For connecting to the local UMLS PostgreSQL DB
import requests  # For making API calls to the LLM
from neo4j import GraphDatabase # The official Neo4j driver
from sentence_transformers import SentenceTransformer # For creating vector embeddings


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
# STEP 2.5: LLM INITIALIZATION
# Initialize AWS Bedrock LLM for entity extraction
# =============================================================================
def initialize_llm():
    """
    Initialize AWS Bedrock LLM (Claude Sonnet 4) for medical entity extraction.
    Returns a LlamaIndex LLM object.
    """
    try:
        from llama_index.llms.bedrock import Bedrock
        
        llm = Bedrock(
            model="anthropic.claude-sonnet-4-20250514-v1:0",
            region_name=AWS_REGION,
            temperature=0.1,
            max_tokens=4096,
            additional_kwargs={
                "top_p": 0.9,
            }
        )
        print("✅ AWS Bedrock LLM initialized successfully")
        return llm
    except Exception as e:
        print(f"❌ Error initializing LLM: {e}")
        print("Falling back to OpenAI...")
        try:
            from llama_index.llms.openai import OpenAI
            llm = OpenAI(
                model="gpt-4o-mini",
                temperature=0.1,
                max_tokens=4096
            )
            print("✅ OpenAI LLM initialized as fallback")
            return llm
        except Exception as e2:
            print(f"❌ Failed to initialize fallback LLM: {e2}")
            raise RuntimeError("Could not initialize any LLM. Check your AWS/OpenAI credentials.")

print("LLM initialization function defined.")


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

-SCHEMA DEFINITION-
Node Types: {node_types}
Relationship Types: {relationship_types}

-EXTRACTION STEPS-
1.  **Identify Entities:** Carefully read the text and identify all terms that match one of the node types in the schema. For each entity, you must extract:
    - `entity_name`: The exact name of the entity as it appears in the text.
    - `entity_type`: The corresponding type from the schema's Node Types list.
    - `entity_description`: A concise, one-sentence description of the entity based on its context in the text.

2.  **Identify Relationships:** Identify all relationships between the entities you found. The relationship must match one of the types in the schema. For each relationship, you must extract:
    - `source_entity_name`: The name of the source entity.
    - `source_entity_type`: The type of the source entity.
    - `target_entity_name`: The name of the target entity.
    - `target_entity_type`: The type of the target entity.
    - `relation_type`: The corresponding type from the schema's Relationship Types list.
    - `relationship_description`: A concise, one-sentence explanation of the relationship based on the text.

-OUTPUT FORMATTING-
1.  **CRITICAL:** Your entire response must be ONLY a single, valid JSON object. Do not include any introductory text, greetings, or markdown formatting like ```json.
2.  The JSON object must have two primary keys: "entities" and "relationships".
3.  The value for each key must be a list of JSON objects, where each object follows the structure defined in the EXTRACTION STEPS.
4.  If no entities or relationships are found, return an empty list for the corresponding key.

-EXAMPLE OF THE EXACT JSON STRUCTURE REQUIRED-
```json
{{
  "entities": [
    {{"entity_name": "Example Disease", "entity_type": "Disease", "entity_description": "A sample description."}}
  ],
  "relationships": [
    {{"source_entity_name": "Example Disease", "source_entity_type": "Disease", "target_entity_name": "Example Symptom", "target_entity_type": "Symptom", "relation_type": "HAS_SYMPTOM", "relationship_description": "A sample relationship description."}}
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


# --- A simple dictionary for common, unambiguous abbreviations ---
# This can be expanded over time.
ABBREVIATION_MAP = {
    "MI": "Myocardial Infarction",
    "HBP": "High Blood Pressure",
    "CD": "Conduct Disorder",
    "ADHD": "Attention-Deficit/Hyperactivity Disorder",
    "CT": "Computed Tomography",
    "MRI": "Magnetic Resonance Imaging",
}

def clean_description(description: str) -> str:
    """Removes the semantic tag like (finding) from the end of a description."""
    return re.sub(r'\s\([^)]+\)$', '', description).strip()

# =============================================================================
# FINAL, MOST ROBUST STANDARDIZATION FUNCTION (v1.4 - Context-Aware)
# =============================================================================

def standardize_entity(entity_name: str, entity_type: str, aws_client) -> dict:
    """
    Enhanced standardization with dual-API fallback mechanism.
    
    Strategy:
    1. Try primary API (SNOMED or RxNorm based on entity type)
    2. If no confident match, try secondary API (the other one)  
    3. Confidence scoring filters false positives
    4. Final fallback to deterministic ID
    """
    # 1. Abbreviation Expansion
    expanded_name = ABBREVIATION_MAP.get(entity_name.upper(), entity_name)
    primary_api = ENTITY_TYPE_TO_API_MAP.get(entity_type)

    if not primary_api:
        fallback_id = generate_fallback_id(entity_name, entity_type)
        return {"ontology_id": fallback_id, "standard_name": entity_name.title()}

    # 2. Create context-rich string for the API
    text_for_api = f"{expanded_name} ({entity_type})"

    # 3. Define API calling function
    def try_api(api_name: str):
        """Helper function to call either SNOMED or RxNorm API."""
        try:
            if api_name == "snomed":
                response = aws_client.infer_snomedct(Text=text_for_api)
                entities = response.get('Entities', [])
                concept_key = 'SNOMEDCTConcepts'
                api_prefix = 'SNOMEDCT'
            elif api_name == "rxnorm":
                response = aws_client.infer_rx_norm(Text=text_for_api)
                entities = response.get('Entities', [])
                concept_key = 'RxNormConcepts'
                api_prefix = 'RXNORM'
            else:
                return None

            # Find the best concept from the response
            best_concept = None
            highest_score = 0.0

            if entities:
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
            return None

        except Exception as e:
            print(f"  - AWS {api_name.upper()} API Error for '{entity_name}': {e}")
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
        return []

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
def process_text_chunk(text_chunk: str, llm, aws_client, umls_cursor, embedding_model) -> dict:
    """
    Orchestrates the entire enrichment pipeline for a single chunk of text.
    """
    print("  - Sending chunk to LLM for initial extraction")

    # 1. Initial Extraction with Live LLM
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        node_types=', '.join(COMPREHENSIVE_SCHEMA['node_types']),
        relationship_types=', '.join(COMPREHENSIVE_SCHEMA['relationship_types']),
        text_chunk=text_chunk
    )
    try:
        response = llm.complete(prompt)
        llm_output_text = response.text
        # print("LLM response: ", llm_output_text)
    except Exception as e:
        print(f"  - LLM API Error: {e}")
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
    except json.JSONDecodeError:
        print("  - ERROR: LLM did not return a valid JSON object.")
        print("  - Raw LLM Output:\n", llm_output_text)
        return {"nodes": [], "relationships": []}


    # 3. Enrich Entities
    enriched_nodes = {}
    entity_to_id_map = {}
    if entities:
        print(f"  - Standardizing and enriching {len(entities)} entities...")
        for entity in entities:
            # Use a tuple to handle cases where the same name might have different types
            entity_key = (entity['entity_name'], entity['entity_type'])

            standard_info = standardize_entity(entity['entity_name'], entity['entity_type'], aws_client)
            ontology_id = standard_info['ontology_id']

            if ontology_id not in enriched_nodes:
                # Use hybrid synonym lookup with original entity information
                synonyms = get_synonyms(
                    ontology_id=ontology_id,
                    umls_cursor=umls_cursor,
                    original_entity_name=entity['entity_name'],
                    entity_type=entity['entity_type']
                )
                summary = f"Concept: {standard_info['standard_name']}. Description: {entity['entity_description']}"
                embedding = get_embedding(summary, embedding_model)

                # Combine original entity name with found synonyms (deduplicated)
                all_synonyms = list(set([entity['entity_name']] + synonyms))

                enriched_nodes[ontology_id] = {
                    "ontology_id": ontology_id,
                    "label": entity['entity_type'],
                    "standard_name": standard_info['standard_name'],
                    "synonyms": all_synonyms,
                    "description": entity['entity_description'],
                    "embedding": embedding
                }
            entity_to_id_map[entity_key] = ontology_id

    # 4. Map Relationships using the generated IDs
    enriched_relationships = []
    if relationships:
        print(f"  - Mapping {len(relationships)} relationships...")
        for rel in relationships:
            source_key = (rel['source_entity_name'], rel['source_entity_type'])
            target_key = (rel['target_entity_name'], rel['target_entity_type'])

            source_id = entity_to_id_map.get(source_key)
            target_id = entity_to_id_map.get(target_key)

            if source_id and target_id:
                enriched_relationships.append({
                    "source_id": source_id,
                    "target_id": target_id,
                    "label": rel['relation_type'],
                    "description": rel['relationship_description']
                })

    return {"nodes": list(enriched_nodes.values()), "relationships": enriched_relationships}

print("Enrichment pipeline functions defined.")

# =============================================================================
# Step 6: REFINED DATABASE LOADING FUNCTIONS
# =============================================================================

# =============================================================================
# REFINED DATABASE LOADING FUNCTIONS (v1.1 - Syntax Fix)
# =============================================================================

def load_nodes_to_neo4j(tx, nodes):
    """
    Loads a batch of nodes into Neo4j using a robust MERGE and SET pattern.
    This version includes the correct WITH clause syntax.
    """
    # This query is idempotent and handles updates.
    query = """
    UNWIND $nodes as node_data
    // Find or create the node based on its unique ontology_id
    MERGE (n {ontology_id: node_data.ontology_id})
    // Set all properties on the node. This works for both CREATE and MATCH.
    SET n += {
        standard_name: node_data.standard_name,
        synonyms: node_data.synonyms,
        description: node_data.description,
        embedding: node_data.embedding
    }
    // Correctly pass the context to the next clause
    WITH n, node_data.label AS label
    // Dynamically add the label to the node
    CALL apoc.create.addLabels(n, [label]) YIELD node
    RETURN count(node)
    """
    tx.run(query, nodes=nodes)

# The load_relationships_to_neo4j function remains the same.
def load_relationships_to_neo4j(tx, relationships):
    """Loads a batch of relationships into Neo4j."""
    query = """
    UNWIND $relationships as rel_data
    MATCH (source {ontology_id: rel_data.source_id})
    MATCH (target {ontology_id: rel_data.target_id})
    CALL apoc.merge.relationship(source, rel_data.label, {}, {
        evidence_text: rel_data.description,
        source_document: $source_document_name
    }, target) YIELD rel
    RETURN count(rel)
    """
    tx.run(query, relationships=relationships, source_document_name=SOURCE_DOCUMENT_NAME)
    
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