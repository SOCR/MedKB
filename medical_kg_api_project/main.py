# ==============================================================================
# main.py (Production Version - Final API Design)
#
# This version implements the best practice for search and retrieval workflows.
# The /search/nodes endpoint now returns the UUID for each result, enabling
# clients to perform subsequent actions without an extra lookup step.
# ==============================================================================

import os
import re
import json
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any

# LlamaIndex Imports
from llama_index.core import Settings, PromptTemplate
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.indices.property_graph import (
    TextToCypherRetriever,
    VectorContextRetriever,
    LLMSynonymRetriever,
)

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
    title="Medical Knowledge Graph API",
    description="A versatile API for all types of graph queries.",
    version="3.7.0", # Version bump for response parsing
)

# --- Global Variables & Initialization ---
graph_store: Neo4jPropertyGraphStore | None = None
cypher_retriever: TextToCypherRetriever | None = None
synonym_retriever: LLMSynonymRetriever | None = None
vector_retriever: VectorContextRetriever | None = None
SEMANTIC_LABELS = "Disease", "Symptom", "Medication", "Treatment"

# Prompt to generate a case-insensitive query
CYPHER_GENERATION_TEMPLATE = PromptTemplate(
    """
Task: Generate a Cypher statement to query a graph database.
Instructions:
1. Use only the provided relationship types and properties in the schema. Do not use any others.
2. For all string property checks, use `toLower()` for case-insensitive matching.
   - E.g., transform `WHERE n.name = 'Penicillin'` to `WHERE toLower(n.name) = 'penicillin'`.
   - Transform `MATCH (m:Medication {{name: 'Penicillin'}})` to `MATCH (m:Medication) WHERE toLower(m.name) = 'penicillin'`.
3. **Relationship Direction:** By default, use non-directional relationships, like `-[r]-`.
4. Return name and description of the nodes and relationships.
5. Do not include any explanations, apologies, or text other than the single, complete Cypher statement.

Schema:
{schema}

The question is:
{question}
"""
)

# Prompt to define the combined output format
DEFAULT_CYPHER_RESPONSE_TEMPLATE = PromptTemplate(
    "Generated Cypher query:\n{query}\n\nCypher Response:\n{response}"
)

# *** NEW: Improved prompt for the Synonym Retriever ***
# Improved prompt for the Synonym generation
SYNONYM_GENERATION_PROMPT = PromptTemplate(
    """
You are an expert in medical terminology. Your task is to generate a list of synonyms and related keywords for a given medical term.
Include the original term in the list.
Consider common names, scientific names, abbreviations, and related concepts.
Provide all terms separated by a '^' symbol.

Example:
QUERY: high blood pressure
KEYWORDS: Hypertension^HBP^High blood pressure

QUERY: {query_str}
KEYWORDS:
"""
)


@app.on_event("startup")
def startup_event():
    """
    Initializes database connection, LLM, and the Text-to-Cypher retriever.
    """
    global graph_store, cypher_retriever

    NEO4J_URL = os.getenv("NEO4J_URL")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    if not all([NEO4J_URL, NEO4J_USERNAME, NEO4J_PASSWORD, OPENAI_API_KEY]):
        raise RuntimeError("FATAL: Missing one or more required environment variables.")
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

    print("INFO: Initializing all services...")
    try:
        Settings.llm = OpenAI(model="gpt-4", temperature=0)
        Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")

        graph_store = Neo4jPropertyGraphStore(
            url=NEO4J_URL, username=NEO4J_USERNAME, password=NEO4J_PASSWORD, database="neo4j"
        )
        
        cypher_retriever = TextToCypherRetriever(
            graph_store,
            llm=Settings.llm,
            text_to_cypher_template=CYPHER_GENERATION_TEMPLATE,
            response_template=DEFAULT_CYPHER_RESPONSE_TEMPLATE,
        )
        
        for label in SEMANTIC_LABELS:
            execute_cypher(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.uuid IS UNIQUE")

        print("INFO: All services initialized successfully.")
    except Exception as e:
        print(f"FATAL: Error during initialization: {e}")
        raise RuntimeError(f"Could not initialize services: {e}")

# --- Helper Function to Execute Cypher ---
def execute_cypher(cypher: str, params: dict = {}) -> List[Dict[str, Any]]:
    if not graph_store:
        raise HTTPException(status_code=503, detail="Graph store is not initialized.")
    try:
        driver = graph_store._driver
        records, _, _ = driver.execute_query(cypher, parameters_=params)
        return [record.data() for record in records]
    except Exception as e:
        print(f"Error executing Cypher: {e}")
        raise HTTPException(status_code=500, detail="Error executing Cypher query.")


# --- API Endpoints ---

@app.get("/", summary="Health Check", tags=["General"])
def read_root():
    return {"status": "ok"}

@app.get("/search/nodes", response_model=List[SearchResult], summary="Fuzzy Search for Nodes (Autocomplete)", tags=["Search & Exploration"])
def fuzzy_search_nodes(q: str = Query(..., min_length=3, description="The search term to find similar nodes for.")):
    """
    Performs a fuzzy search to find nodes with names similar to the query term.
    Crucially, it returns the stable UUID for each node so clients can perform
    further actions.
    """
    # *** FIX: The query now returns n.uuid for use in subsequent API calls. ***
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
    The workhorse for graph visualization. Fetches a central node and its neighbors
    using its stable, unique UUID.
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

# --- The specialized tool endpoints remain the same as they already work with names.

@app.get("/disease/{disease_name}/symptoms", summary="Get Symptoms for a Disease", tags=["Specialized Tools"])
def get_symptoms_for_disease(disease_name: str) -> List[Dict[str, Any]]:
    cypher = "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(d.name) = toLower($name) RETURN s.name as name, s.description as description"
    params = {"name": disease_name}
    return execute_cypher(cypher, params)

@app.get("/disease/{disease_name}/medications", summary="Get Medications for a Disease", tags=["Specialized Tools"])
def get_medications_for_disease(disease_name: str) -> List[Dict[str, Any]]:
    cypher = "MATCH (d:Disease)-[:TREATED_BY]->(m:Medication) WHERE toLower(d.name) = toLower($name) RETURN m.name as name, m.description as description"
    params = {"name": disease_name}
    return execute_cypher(cypher, params)

@app.get("/medication/{medication_name}/treats", summary="Get Diseases Treated by a Medication", tags=["Specialized Tools"])
def get_diseases_for_medication(medication_name: str) -> List[Dict[str, Any]]:
    cypher = "MATCH (d:Disease)-[:TREATED_BY]->(m:Medication) WHERE toLower(m.name) = toLower($name) RETURN d.name as name, d.description as description"
    params = {"name": medication_name}
    return execute_cypher(cypher, params)

@app.get("/symptom/{symptom_name}/is_symptom_of", summary="Get Diseases Associated with a Symptom", tags=["Specialized Tools"])
def get_diseases_for_symptom(symptom_name: str) -> List[Dict[str, Any]]:
    cypher = "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(s.name) = toLower($name) RETURN d.name as name, d.description as description"
    params = {"name": symptom_name}
    return execute_cypher(cypher, params)


@app.post("/query/graph", summary="The 'Graph Analyst' (Text-to-Cypher)", tags=["Smart Querying"])
def query_graph(request: NaturalLanguageQueryRequest) -> Dict[str, Any]:
    """
    Answers complex, multi-hop questions by generating a robust, case-insensitive
    Cypher query and returning its direct results from the database.
    """
    if not cypher_retriever:
        raise HTTPException(status_code=503, detail="Text-to-Cypher retriever is not initialized.")
    
    try:
        # The retriever now executes the query and returns a formatted string.
        retrieved_nodes = cypher_retriever.retrieve(request.question)

        if not retrieved_nodes:
            raise HTTPException(status_code=500, detail="Failed to retrieve response from graph.")

        response_text = retrieved_nodes[0].text.strip()
        
        # *** FIX: Use regex to parse the combined response from the retriever ***
        cypher_query = "Cypher query not parsed."
        database_response_str = "Database response not parsed."

        query_match = re.search(r"Generated Cypher query:\n(.*?)\n\nCypher Response:", response_text, re.DOTALL)
        if query_match:
            cypher_query = query_match.group(1).strip()
        
        response_match = re.search(r"Cypher Response:\n(.*)", response_text, re.DOTALL)
        if response_match:
            database_response_str = response_match.group(1).strip()

        # Try to load the database response string as JSON
        try:
            database_response = json.loads(database_response_str)
        except json.JSONDecodeError:
            database_response = database_response_str
        
        return {
            "question": request.question,
            "generated_cypher": cypher_query,
            "database_response": database_response,
            "raw_response": response_text
        }
    except Exception as e:
        print(f"Error in /query/graph: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing graph query: {e}")

@app.get("/search/semantic", summary="The 'Concept Explorer' (Vector Search)", tags=["Smart Querying"])
def search_semantic(q: str = Query(..., description="A concept or phrase to search for.")):
    """
    Finds nodes that are conceptually similar to the query, not just keyword matches.
    Example: 'treatments for heart problems'
    """
    if not vector_retriever:
        raise HTTPException(status_code=503, detail="Vector retriever is not initialized.")
    
    try:
        retrieved_nodes = vector_retriever.retrieve(q)
        # The retriever returns NodeWithScore objects. We format them for the API response.
        return [{"node_name": n.text, "score": n.score} for n in retrieved_nodes]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during semantic search: {e}")

@app.get("/search/synonyms", response_model=SynonymSearchResponse, summary="The 'Keyword Expander' (Synonym Search)", tags=["Smart Querying"])
def search_synonyms(q: str = Query(..., description="A term to expand with synonyms.")):
    """
    Uses an LLM to generate synonyms for a term and then performs a case-insensitive
    keyword search for all of those terms in the graph.
    Example: 'HBP' or 'High blood pressure'
    """
    if not Settings.llm:
        raise HTTPException(status_code=503, detail="LLM is not initialized.")
    
    try:
        # Step 1: Use the LLM to generate keywords from the custom prompt
        prompt = SYNONYM_GENERATION_PROMPT.format(query_str=q)
        response = Settings.llm.complete(prompt)
        keywords = [k.strip() for k in response.text.strip().split("^")]

        if not keywords:
            return {"query": q, "keywords": [], "results": []}

        # Step 2: Use the generated keywords in a robust Cypher query
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
        print(f"Error in /search/synonyms: {e}")
        raise HTTPException(status_code=500, detail=f"Error during synonym search: {e}")