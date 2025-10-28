import os
import json
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from neo4j import GraphDatabase
import openai

# --- API Data Models ---
class NodeDetail(BaseModel):
    name: str
    label: str
    all_labels: List[str]
    properties: Dict[str, Any]

class GraphNode(BaseModel):
    id: str
    name: str
    label: str
    all_labels: List[str]
    properties: Dict[str, Any]

class GraphLink(BaseModel):
    source: str
    target: str
    label: str

class GraphVicinityResponse(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]

class SearchResult(BaseModel):
    uuid: str
    name: str
    label: str
    all_labels: List[str]
    score: float = Field(..., description="Similarity score from 0.0 to 1.0 (higher is better).")

class NaturalLanguageQueryRequest(BaseModel):
    question: str = Field(..., description="A question in natural language.")

class SynonymSearchResponse(BaseModel):
    query: str
    keywords: List[str]
    results: List[Dict[str, Any]]

# --- FastAPI Application Setup ---
app = FastAPI(
    title="Medical Knowledge Graph API (Production)",
    description="A high-performance, simplified API for querying a medical knowledge graph using direct Neo4j and OpenAI integration.",
    version="5.0.0",
)

# --- Global Variables ---
neo4j_driver = None
openai_client = None
SEMANTIC_LABELS = ["Disease", "Symptom", "Medication", "Treatment"]

def initialize_services():
    """Initialize database connection and OpenAI client if not already done."""
    global neo4j_driver, openai_client
    
    # Return early if already initialized
    if neo4j_driver is not None and openai_client is not None:
        return
    
    NEO4J_URL = os.getenv("NEO4J_URL")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME") 
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    if not all([NEO4J_URL, NEO4J_USERNAME, NEO4J_PASSWORD, OPENAI_API_KEY]):
        raise RuntimeError("Missing required environment variables")
    
    print("INFO: Initializing services...")
    try:
        # Direct Neo4j driver
        if neo4j_driver is None:
            neo4j_driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
            neo4j_driver.verify_connectivity()
            print("INFO: Neo4j connection initialized successfully.")
        
        # Direct OpenAI client - using official approach
        if openai_client is None:
            print(f"INFO: Attempting to initialize OpenAI client with version: {openai.__version__}")
            try:
                # Set the API key as environment variable (required for auto-detection)
                os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
                
                # Official initialization method - reads from environment automatically
                from openai import OpenAI
                openai_client = OpenAI()
                print("INFO: OpenAI client initialized successfully using official method.")
            except Exception as e:
                print(f"ERROR: Could not initialize OpenAI client: {e}")
                print(f"ERROR: Exception type: {type(e)}")
                print(f"ERROR: Exception args: {e.args}")
                # Set a placeholder so we know we tried
                openai_client = "FAILED"
        
    except Exception as e:
        print(f"FATAL: Error during initialization: {e}")
        raise RuntimeError(f"Could not initialize services: {e}")

def execute_cypher(cypher: str, params: dict = {}) -> List[Dict[str, Any]]:
    """Execute Cypher query and return results."""
    # Initialize services if needed
    initialize_services()
    
    if not neo4j_driver:
        raise HTTPException(status_code=503, detail="Database not initialized.")
    
    try:
        with neo4j_driver.session() as session:
            result = session.run(cypher, params)
            return [record.data() for record in result]
    except Exception as e:
        print(f"Error executing Cypher: {e}")
        raise HTTPException(status_code=500, detail="Database query failed.")

def generate_cypher_with_openai(question: str) -> str:
    """Generate Cypher query using OpenAI."""
    # Initialize services if needed
    initialize_services()
    
    if not openai_client or openai_client == "FAILED":
        raise HTTPException(status_code=503, detail="OpenAI client not initialized.")
    
    prompt = f"""
Task: Generate a Cypher statement to query a graph database.
Instructions:
1. Use only the provided relationship types and properties in the schema.
2. For all string property checks, use `toLower()` for case-insensitive matching.
3. Use non-directional relationships like `-[r]-`.
4. Return name and description of nodes and relationships.
5. Return ONLY the Cypher statement, no explanations.

Schema:
Node labels: Disease, Symptom, Medication, Treatment
Relationships: HAS_SYMPTOM, TREATED_BY, INTERACTS_WITH
Properties: name, description, uuid

Question: {question}
"""
    
    try:
        # Use v1.x API syntax with latest model
        response = openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        # Log the full error for debugging
        print(f"FATAL: OpenAI API error in generate_cypher: {e}")
        print(f"FATAL: Exception Type: {type(e)}")
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")

def generate_synonyms_with_openai(query: str) -> List[str]:
    """Generate synonyms using OpenAI."""
    # Initialize services if needed
    initialize_services()
    
    if not openai_client or openai_client == "FAILED":
        print("OpenAI client not initialized, using fallback")
        return [query]  # Fallback to original query
    
    prompt = f"""
You are an expert in medical terminology. Generate synonyms and related keywords for this medical term.
Include the original term, common names, scientific names, and abbreviations.
Return terms separated by '^' symbol.

Example:
QUERY: high blood pressure  
KEYWORDS: Hypertension^HBP^High blood pressure

QUERY: {query}
KEYWORDS:
"""
    
    try:
        # Use v1.x API syntax with latest model
        response = openai_client.chat.completions.create(
            model="gpt-4.1", 
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        keywords = response.choices[0].message.content.strip()
        return [k.strip() for k in keywords.split("^") if k.strip()]
    except Exception as e:
        print(f"FATAL: Error generating synonyms: {e}")
        print(f"FATAL: Exception Type: {type(e)}")
        # Return a more specific error message
        raise HTTPException(status_code=500, detail=f"OpenAI API error during synonym generation: {str(e)}")

# --- API Endpoints ---

@app.get("/", summary="Health Check", tags=["General"])
def read_root():
    """
    Performs a health check on the API and its dependent services (Neo4j, OpenAI).
    Returns the status of each service, which is useful for monitoring.
    """
    # Try to initialize services
    try:
        initialize_services()
        services_status = {
            "neo4j": neo4j_driver is not None,
            "openai": openai_client is not None and openai_client != "FAILED"
        }
        
        # Add debugging info
        if openai_client == "FAILED":
            services_status["openai_debug"] = "Initialization failed - check logs"
        elif openai_client is not None:
            services_status["openai_version"] = openai.__version__
            
    except Exception as e:
        services_status = {
            "neo4j": False,
            "openai": False,
            "error": str(e)
        }
    
    return {
        "status": "ok", 
        "version": "5.0.0-simplified-latest",
        "services": services_status
    }

@app.get("/search/nodes", response_model=List[SearchResult], summary="Fuzzy Search for Nodes (Autocomplete)", tags=["Search & Exploration"])
def fuzzy_search_nodes(q: str = Query(..., min_length=3, description="The search term to find similar nodes for.")):
    """
    Performs a fuzzy search using Levenshtein distance to find nodes with names
    similar to the query term. Ideal for autocomplete features.
    
    Returns the stable UUID for each node so clients can perform further actions.
    """
    cypher = """
    MATCH (n)
    WHERE ANY(label IN labels(n) WHERE label IN $semantic_labels) AND n.name IS NOT NULL
    WITH n, apoc.text.levenshteinSimilarity(toLower(n.name), toLower($query_term)) AS score
    WHERE score > 0.6
    WITH n, score, [label IN labels(n) WHERE label IN $semantic_labels] as semantic_labels
    RETURN n.uuid as uuid, 
           n.name AS name,
           CASE
               WHEN 'Disease' IN semantic_labels THEN 'Disease'
               WHEN 'Medication' IN semantic_labels THEN 'Medication'
               WHEN 'Treatment' IN semantic_labels THEN 'Treatment'
               ELSE semantic_labels[0]
           END AS label,
           semantic_labels as all_labels,
           score
    ORDER BY score DESC
    LIMIT 7
    """
    params = {"query_term": q, "semantic_labels": SEMANTIC_LABELS}
    return execute_cypher(cypher, params)

@app.get("/node/{uuid}/details", response_model=NodeDetail, summary="Get Details for a Single Node by UUID", tags=["Search & Exploration"])
def get_node_details(uuid: str):
    """Retrieves all properties for a single semantic node by its stable UUID."""
    cypher = """
    MATCH (n) 
    WHERE n.uuid = $uuid
    WITH n, [label IN labels(n) WHERE label IN $semantic_labels] as semantic_labels
    RETURN n.name as name,
           CASE
               WHEN 'Disease' IN semantic_labels THEN 'Disease'
               WHEN 'Medication' IN semantic_labels THEN 'Medication'
               WHEN 'Treatment' IN semantic_labels THEN 'Treatment'
               ELSE semantic_labels[0]
           END as label,
           semantic_labels as all_labels,
           properties(n) as properties
    LIMIT 1
    """
    params = {"uuid": uuid, "semantic_labels": SEMANTIC_LABELS}
    result = execute_cypher(cypher, params)
    if not result:
        raise HTTPException(status_code=404, detail="Node not found.")
    return result[0]

@app.get("/graph/vicinity/{uuid}", response_model=GraphVicinityResponse, summary="Get Node and its Neighbors by UUID", tags=["Search & Exploration"])
def get_graph_vicinity(uuid: str):
    """
    The workhorse for graph visualization. Fetches a central node and its immediate
    neighbors using its stable, unique UUID.
    """
    cypher = """
    MATCH (a)
    WHERE a.uuid = $uuid
    OPTIONAL MATCH (a)-[r]-(b)
    WHERE ANY(label IN labels(b) WHERE label IN $semantic_labels) AND b.name IS NOT NULL
    WITH a, collect(b) as neighbors, collect(r) as rels
    WITH [a] + neighbors as all_nodes, rels
    UNWIND all_nodes as n
    WITH collect(DISTINCT {
        id: n.uuid, 
        name: n.name,
        label: CASE
                   WHEN 'Disease' IN labels(n) THEN 'Disease'
                   WHEN 'Medication' IN labels(n) THEN 'Medication'
                   WHEN 'Treatment' IN labels(n) THEN 'Treatment'
                   ELSE [l IN labels(n) WHERE l IN $semantic_labels][0]
               END,
        all_labels: [l IN labels(n) WHERE l IN $semantic_labels],
        properties: properties(n)
    }) as nodes, rels
    UNWIND rels as r
    WITH nodes, collect(DISTINCT {source: startNode(r).uuid, target: endNode(r).uuid, label: type(r)}) as links
    RETURN nodes, links
    """
    params = {"uuid": uuid, "semantic_labels": SEMANTIC_LABELS}
    result = execute_cypher(cypher, params)
    if not result or not result[0]['nodes']:
        raise HTTPException(status_code=404, detail="Node not found or has no valid connections.")
    return result[0]

@app.post("/query/graph", summary="The 'Graph Analyst' (Text-to-Cypher)", tags=["Smart Querying"])
def query_graph(request: NaturalLanguageQueryRequest) -> Dict[str, Any]:
    """
    Answers complex, multi-hop questions by generating a Cypher query from
    natural language, executing it, and returning the direct database results.
    """
    initialize_services()
    cypher_query = generate_cypher_with_openai(request.question)
    
    return {
        "question": request.question,
        "generated_cypher": cypher_query,
        "database_response": execute_cypher(cypher_query)
    }

@app.get("/search/synonyms", response_model=SynonymSearchResponse, summary="The 'Keyword Expander' (Synonym Search)", tags=["Smart Querying"])
def search_synonyms(q: str = Query(..., description="A term to expand with synonyms.")):
    """
    Uses an LLM to generate synonyms for a medical term, then performs a
    case-insensitive keyword search for all generated terms in the graph.
    Example: 'HBP' or 'High blood pressure'
    """
    initialize_services()
    keywords = generate_synonyms_with_openai(q)

    cypher = """
    UNWIND $keywords as keyword
    MATCH (n)
    WHERE ANY(label IN labels(n) WHERE label IN $semantic_labels) 
          AND toLower(n.name) CONTAINS toLower(keyword)
    WITH n, keyword
    WITH n, [label IN labels(n) WHERE label IN $semantic_labels] as semantic_labels
    RETURN DISTINCT n.uuid as uuid, 
           n.name AS name,
           CASE
               WHEN 'Disease' IN semantic_labels THEN 'Disease'
               WHEN 'Medication' IN semantic_labels THEN 'Medication'
               WHEN 'Treatment' IN semantic_labels THEN 'Treatment'
               ELSE semantic_labels[0]
           END AS label,
           semantic_labels as all_labels,
           1.0 as score
    LIMIT 20
    """
    params = {"keywords": keywords, "semantic_labels": SEMANTIC_LABELS}
    results = execute_cypher(cypher, params)
    
    return {
        "query": q,
        "keywords": keywords,
        "results": results
    }

@app.get("/disease/{disease_name}/symptoms", summary="Get Symptoms for a Disease", tags=["Specialized Tools"])
def get_symptoms_for_disease(disease_name: str) -> List[Dict[str, Any]]:
    """Retrieves all symptoms directly associated with a given disease."""
    cypher = "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(d.name) = toLower($name) RETURN s.name as name, s.description as description"
    return execute_cypher(cypher, {"name": disease_name})

@app.get("/disease/{disease_name}/medications", summary="Get Medications for a Disease", tags=["Specialized Tools"])
def get_medications_for_disease(disease_name: str) -> List[Dict[str, Any]]:
    """Retrieve all medications used to treat a given disease."""
    cypher = "MATCH (d:Disease)-[:TREATED_BY]->(m:Medication) WHERE toLower(d.name) = toLower($name) RETURN m.name as name, m.description as description"
    return execute_cypher(cypher, {"name": disease_name})

@app.get("/medication/{medication_name}/treats", summary="Get Diseases Treated by a Medication", tags=["Specialized Tools"])
def get_diseases_for_medication(medication_name: str) -> List[Dict[str, Any]]:
    """Retrieves all diseases treated by a given medication."""
    cypher = "MATCH (d:Disease)-[:TREATED_BY]->(m:Medication) WHERE toLower(m.name) = toLower($name) RETURN d.name as name, d.description as description"
    return execute_cypher(cypher, {"name": medication_name})

@app.get("/symptom/{symptom_name}/is_symptom_of", summary="Get Diseases Associated with a Symptom", tags=["Specialized Tools"])
def get_diseases_for_symptom(symptom_name: str) -> List[Dict[str, Any]]:
    """Retrieves all diseases that list the given symptom."""
    cypher = "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(s.name) = toLower($name) RETURN d.name as name, d.description as description"
    return execute_cypher(cypher, {"name": symptom_name}) 