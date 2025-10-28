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
    title="Medical Knowledge Graph API (Simplified)",
    description="Fast API with direct Neo4j and OpenAI integration",
    version="4.0.0",
)

# --- Global Variables ---
neo4j_driver = None
openai_client = None
SEMANTIC_LABELS = ["Disease", "Symptom", "Medication", "Treatment"]

@app.on_event("startup")
def startup_event():
    """Initialize database connection and OpenAI client."""
    global neo4j_driver, openai_client
    
    NEO4J_URL = os.getenv("NEO4J_URL")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME") 
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    if not all([NEO4J_URL, NEO4J_USERNAME, NEO4J_PASSWORD, OPENAI_API_KEY]):
        raise RuntimeError("Missing required environment variables")
    
    print("INFO: Initializing services...")
    try:
        # Direct Neo4j driver
        neo4j_driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        
        # Direct OpenAI client
        openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        # Test connections
        neo4j_driver.verify_connectivity()
        
        print("INFO: All services initialized successfully.")
    except Exception as e:
        print(f"FATAL: Error during initialization: {e}")
        raise RuntimeError(f"Could not initialize services: {e}")

@app.on_event("shutdown")
def shutdown_event():
    """Clean up connections."""
    if neo4j_driver:
        neo4j_driver.close()

def execute_cypher(cypher: str, params: dict = {}) -> List[Dict[str, Any]]:
    """Execute Cypher query and return results."""
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
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {e}")

def generate_synonyms_with_openai(query: str) -> List[str]:
    """Generate synonyms using OpenAI."""
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
        response = openai_client.chat.completions.create(
            model="gpt-4", 
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        keywords = response.choices[0].message.content.strip()
        return [k.strip() for k in keywords.split("^") if k.strip()]
    except Exception as e:
        print(f"Error generating synonyms: {e}")
        return [query]  # Fallback to original query

# --- API Endpoints ---

@app.get("/", summary="Health Check")
def read_root():
    return {"status": "ok", "version": "4.0.0-simplified"}

@app.get("/search/nodes", response_model=List[SearchResult])
def fuzzy_search_nodes(q: str = Query(..., min_length=3)):
    """Fuzzy search for nodes with autocomplete functionality."""
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

@app.get("/node/{uuid}/details", response_model=NodeDetail)
def get_node_details(uuid: str):
    """Get detailed information for a node by UUID."""
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

@app.get("/graph/vicinity/{uuid}", response_model=GraphVicinityResponse)
def get_graph_vicinity(uuid: str):
    """Get a node and its immediate neighbors for graph visualization."""
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
        raise HTTPException(status_code=404, detail="Node not found.")
    return result[0]

@app.post("/query/graph")
def query_graph(request: NaturalLanguageQueryRequest) -> Dict[str, Any]:
    """Convert natural language to Cypher and execute query."""
    try:
        # Generate Cypher query
        cypher_query = generate_cypher_with_openai(request.question)
        
        # Execute the generated query
        database_response = execute_cypher(cypher_query)
        
        return {
            "question": request.question,
            "generated_cypher": cypher_query,
            "database_response": database_response
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing failed: {e}")

@app.get("/search/synonyms", response_model=SynonymSearchResponse)
def search_synonyms(q: str = Query(...)):
    """Expand search terms with synonyms and search the graph."""
    try:
        # Generate synonyms
        keywords = generate_synonyms_with_openai(q)
        
        if not keywords:
            return {"query": q, "keywords": [], "results": []}
        
        # Search using all keywords
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Synonym search failed: {e}")

# Specialized endpoints (unchanged)
@app.get("/disease/{disease_name}/symptoms")
def get_symptoms_for_disease(disease_name: str) -> List[Dict[str, Any]]:
    cypher = "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(d.name) = toLower($name) RETURN s.name as name, s.description as description"
    return execute_cypher(cypher, {"name": disease_name})

@app.get("/disease/{disease_name}/medications")
def get_medications_for_disease(disease_name: str) -> List[Dict[str, Any]]:
    cypher = "MATCH (d:Disease)-[:TREATED_BY]->(m:Medication) WHERE toLower(d.name) = toLower($name) RETURN m.name as name, m.description as description"
    return execute_cypher(cypher, {"name": disease_name})

@app.get("/medication/{medication_name}/treats")
def get_diseases_for_medication(medication_name: str) -> List[Dict[str, Any]]:
    cypher = "MATCH (d:Disease)-[:TREATED_BY]->(m:Medication) WHERE toLower(m.name) = toLower($name) RETURN d.name as name, d.description as description"
    return execute_cypher(cypher, {"name": medication_name})

@app.get("/symptom/{symptom_name}/is_symptom_of")
def get_diseases_for_symptom(symptom_name: str) -> List[Dict[str, Any]]:
    cypher = "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(s.name) = toLower($name) RETURN d.name as name, d.description as description"
    return execute_cypher(cypher, {"name": symptom_name}) 