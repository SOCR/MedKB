import requests
import json
import time

# --- Configuration ---
BASE_URL = "https://2ktmhw4hwz6e2djsiil7h2x56m0qgvnm.lambda-url.us-east-1.on.aws"
HEADERS = {"Content-Type": "application/json"}

# --- Helper Functions ---
def print_header(title):
    """Prints a formatted header for each test section."""
    print("\n" + "="*60)
    print(f"🔬 TESTING: {title}")
    print("="*60)

def print_result(response):
    """Prints the status code and JSON response."""
    print(f"▶️  Status Code: {response.status_code}")
    try:
        print("▶️  Response JSON:")
        print(json.dumps(response.json(), indent=2))
    except json.JSONDecodeError:
        print("▶️  Response Text (not JSON):")
        print(response.text)

# --- Test Functions ---

def test_health_check():
    """Tests the root health check endpoint."""
    print_header("Health Check (/}")
    response = requests.get(BASE_URL)
    print_result(response)
    # Check for success
    if response.status_code == 200 and response.json().get("services", {}).get("neo4j") and response.json().get("services", {}).get("openai"):
        print("✅ STATUS: Health check passed!")
        return True
    else:
        print("❌ STATUS: Health check FAILED!")
        return False

def test_search_nodes():
    """Tests the fuzzy node search."""
    print_header("Fuzzy Node Search (/search/nodes)")
    search_term = "headache"
    print(f"Query: {search_term}")
    response = requests.get(f"{BASE_URL}/search/nodes", params={"q": search_term})
    print_result(response)
    
    if response.status_code == 200 and response.json():
        # Try to get a UUID for the next tests
        first_result = response.json()[0]
        if first_result.get("uuid"):
            print(f"✅ STATUS: Search successful. Found UUID: {first_result['uuid']}")
            return first_result["uuid"]
    
    print("❌ STATUS: Node search failed or returned no results.")
    return None

def test_node_details(node_uuid):
    """Tests fetching details for a specific node."""
    print_header("Node Details (/node/{uuid}/details)")
    if not node_uuid:
        print("SKIPPING: No node UUID available from previous test.")
        return
        
    response = requests.get(f"{BASE_URL}/node/{node_uuid}/details")
    print_result(response)
    if response.status_code == 200:
        print("✅ STATUS: Node details fetch successful.")
    else:
        print("❌ STATUS: Node details fetch FAILED!")


def test_graph_vicinity(node_uuid):
    """Tests fetching the graph neighborhood for a node."""
    print_header("Graph Vicinity (/graph/vicinity/{uuid})")
    if not node_uuid:
        print("SKIPPING: No node UUID available from previous test.")
        return

    response = requests.get(f"{BASE_URL}/graph/vicinity/{node_uuid}")
    print_result(response)
    if response.status_code == 200:
        print("✅ STATUS: Graph vicinity fetch successful.")
    else:
        print("❌ STATUS: Graph vicinity fetch FAILED!")

def test_natural_language_query():
    """Tests the text-to-Cypher endpoint."""
    print_header("Natural Language Query (/query/graph)")
    payload = {
        "question": "What are the symptoms of Migraine?"
    }
    print("Question:", payload["question"])
    response = requests.post(f"{BASE_URL}/query/graph", json=payload, headers=HEADERS)
    print_result(response)
    if response.status_code == 200:
        print("✅ STATUS: Natural language query successful.")
    else:
        print("❌ STATUS: Natural language query FAILED!")

def test_synonym_search():
    """Tests the synonym generation and search."""
    print_header("Synonym Search (/search/synonyms)")
    search_term = "hypertension"
    print(f"Query: {search_term}")
    response = requests.get(f"{BASE_URL}/search/synonyms", params={"q": search_term})
    print_result(response)
    if response.status_code == 200:
        print("✅ STATUS: Synonym search successful.")
    else:
        print("❌ STATUS: Synonym search FAILED!")


def test_specialized_queries():
    """Tests all the specific disease/symptom/medication routes."""
    print_header("Specialized Queries")
    
    # Test 1: Get symptoms for a disease
    disease = "Migraine"
    print(f"\n--- Testing: Symptoms for Disease '{disease}' ---")
    response1 = requests.get(f"{BASE_URL}/disease/{disease}/symptoms")
    print_result(response1)
    if response1.status_code != 200: print("❌ FAILED")

    # Test 2: Get medications for a disease
    print(f"\n--- Testing: Medications for Disease '{disease}' ---")
    response2 = requests.get(f"{BASE_URL}/disease/{disease}/medications")
    print_result(response2)
    if response2.status_code != 200: print("❌ FAILED")

    # Test 3: Get diseases for a symptom
    symptom = "Nausea"
    print(f"\n--- Testing: Diseases for Symptom '{symptom}' ---")
    response3 = requests.get(f"{BASE_URL}/symptom/{symptom}/is_symptom_of")
    print_result(response3)
    if response3.status_code != 200: print("❌ FAILED")

# --- Main Execution ---
if __name__ == "__main__":
    print("🚀 STARTING API ENDPOINT TEST SUITE 🚀")
    
    if not test_health_check():
        print("\nHalting tests because health check failed.")
    else:
        # Run search and capture a UUID for subsequent tests
        node_uuid = test_search_nodes()
        time.sleep(1) # small delay

        # Run tests that depend on the UUID
        test_node_details(node_uuid)
        time.sleep(1)
        
        test_graph_vicinity(node_uuid)
        time.sleep(1)

        # Run remaining tests
        test_natural_language_query()
        time.sleep(1)
        
        test_synonym_search()
        time.sleep(1)
        
        test_specialized_queries()

    print("\n🏁 TEST SUITE FINISHED 🏁") 