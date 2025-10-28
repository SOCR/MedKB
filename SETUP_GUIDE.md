# 🚀 BioGraph Pipeline - Setup & Execution Guide

## Quick Status: You're 75% Done! 🎉

This guide will take you from current state to a **fully working knowledge graph pipeline** in about **1-2 hours**.

---

## ✅ What's Already Complete

- ✅ UMLS PostgreSQL database loaded and tested
- ✅ All pipeline code written (`utils.py`)
- ✅ Source data ready (`Biomedical_Knowledgebase.txt`)
- ✅ AWS credentials configured
- ✅ Hybrid synonym lookup implemented
- ✅ Standardization logic working

---

## 🔧 What You Need to Do (5 Tasks)

### **Task 1: Install Neo4j Desktop** (10 minutes)

**Why**: Your knowledge graph needs a database to store nodes and relationships.

**Steps**:
1. Download: https://neo4j.com/download/
2. Install Neo4j Desktop
3. Launch the application
4. Click "New Project" → Name it "medical-kb-project"
5. Click "Add Database" → "Create Local Database"
   - Name: `medical-kb`
   - Password: `qwerty123` (or your choice)
   - Version: 5.x (latest)
6. Click on database → "Plugins" tab → Install **APOC**
7. Click "Start" button
8. Verify it's running (green status)

**Test**:
```python
from neo4j import GraphDatabase
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "qwerty123"))
driver.verify_connectivity()
print("✅ Neo4j connected!")
driver.close()
```

---

### **Task 2: Install Python Dependencies** (5 minutes)

**Why**: Pipeline needs specific packages for building the knowledge graph.

**Steps**:
```bash
# In your Medical-KB directory
pip install -r requirements_pipeline.txt
```

**Note**: We use `requirements_pipeline.txt` (not `requirements.txt`) - see REQUIREMENTS_GUIDE.md for details.

**This installs**:
- `boto3` - AWS services
- `psycopg2-binary` - PostgreSQL connection
- `sentence-transformers` - Vector embeddings
- `llama-index-llms-bedrock` - AWS Bedrock Claude integration

**Verify**:
```python
import boto3
import psycopg2
from sentence_transformers import SentenceTransformer
from llama_index.llms.bedrock import Bedrock
print("✅ All imports successful!")
```

---

### **Task 3: Configure AWS Credentials** (5 minutes)

**Why**: Pipeline uses AWS Comprehend Medical and Bedrock.

**Steps**:
```bash
# Run AWS configure if not done already
aws configure

# Enter your credentials:
# AWS Access Key ID: [your-key]
# AWS Secret Access Key: [your-secret]
# Default region: us-east-1
# Default output format: json
```

**Verify**:
```bash
aws sts get-caller-identity
```

Should return your AWS account info.

---

### **Task 4: Verify UMLS Database** (2 minutes)

**Why**: Pipeline needs UMLS for synonym lookup.

**Test**:
```bash
python test_umls_connection.py
```

**Expected output**:
```
✅ Connected to PostgreSQL
✅ MRCONSO table contains XXX records
✅ Found XXX unique English concepts
```

If this fails, run:
```bash
setup_postgres_umls.bat
```

---

### **Task 5: Run the Pipeline!** (30-60 minutes)

**Why**: This builds your knowledge graph!

**Test Mode (Recommended First)**:
```bash
python run_pipeline.py
```

This will:
- Process first 10 text chunks (test mode)
- Create ~50-100 nodes
- Take ~5-10 minutes
- Verify everything works

**Expected Output**:
```
🧬 BIOGRAPH KNOWLEDGE GRAPH GENERATION PIPELINE
============================================================

📋 STEP 1: Initializing services...
  ✅ AWS Comprehend Medical ready
  ✅ UMLS database connected
  ✅ Neo4j database connected
  ✅ AWS Bedrock LLM initialized successfully
  ✅ Embedding model loaded

✅ All services initialized successfully!

📋 STEP 2: Loading and chunking source document...
  📄 Loaded document: XXX characters
  ✂️  Split into XXX chunks
  ✅ Ready for processing

📋 STEP 3: Processing chunks and building knowledge graph...
  ⚠️  TEST MODE: Processing only first 10 chunks
  
  📦 Batch 1/2 (chunks 1-5)
    🔄 Processing chunk 1/10...
    - Sending chunk to LLM for initial extraction
    - LLM extracted 8 entities and 12 relationships.
    - Standardizing and enriching 8 entities...
    ✅ Hypertension → SNOMEDCT:38341003 (primary snomed, conf: 0.94)
    ...
    ✅ Extracted 8 nodes, 12 relationships
  
  💾 Loading batch to Neo4j...
     Nodes: 15
     Relationships: 24
  ✅ Batch 1 loaded successfully!

🎉 PIPELINE COMPLETED!
============================================================

📊 Summary:
  • Total chunks processed: 10
  • Nodes loaded: 52
  • Relationships loaded: 87

✅ Access your graph at: http://localhost:7474
   Username: neo4j
   Password: qwerty123
```

**Full Production Run**:
1. Open `run_pipeline.py`
2. Change line 169: `TEST_MODE = False`
3. Run: `python run_pipeline.py`
4. Wait 30-60 minutes for full processing

---

## 🎯 After Pipeline Completes

### **Explore Your Graph**:

1. Open Neo4j Browser: http://localhost:7474
2. Login (neo4j / qwerty123)
3. Run queries:

```cypher
// Count nodes by type
MATCH (n)
RETURN labels(n)[0] as NodeType, count(*) as Count
ORDER BY Count DESC

// View some diseases
MATCH (d:Disease)
RETURN d.standard_name, d.synonyms, d.description
LIMIT 10

// Find disease-medication relationships
MATCH (d:Disease)-[r:TREATED_BY]->(m:Medication)
RETURN d.standard_name, r.description, m.standard_name
LIMIT 20

// View graph visualization (sample)
MATCH (d:Disease)-[r]-(n)
RETURN d, r, n
LIMIT 50
```

---

## 🐛 Troubleshooting

### **Issue: "ModuleNotFoundError: No module named 'sentence_transformers'"**
**Solution**:
```bash
pip install sentence-transformers
```

### **Issue: "Neo4j driver error: Could not connect to bolt://localhost:7687"**
**Solution**:
- Open Neo4j Desktop
- Make sure database is **Started** (green play button)
- Check password matches in `utils.py`

### **Issue: "botocore.exceptions.NoCredentialsError"**
**Solution**:
```bash
aws configure
# Enter your AWS credentials
```

### **Issue: "APOC procedure not found"**
**Solution**:
- Neo4j Desktop → Click database
- Plugins tab → Install APOC
- Restart database

### **Issue: "psycopg2.OperationalError: could not connect to server"**
**Solution**:
- Start PostgreSQL service
- Verify connection: `psql -U postgres -d umls`

### **Issue: LLM returns invalid JSON**
**Solution**:
- This is usually temporary
- The pipeline will skip the chunk and continue
- Check your AWS Bedrock quotas

---

## 💰 Estimated AWS Costs (with Credits)

For full pipeline run (~2,000 chunks):

| Service | Usage | Cost |
|---------|-------|------|
| AWS Comprehend Medical | ~2,000 API calls | ~$2-5 |
| AWS Bedrock (Claude) | ~1M tokens | ~$30-50 |
| Lambda (future API) | Minimal | <$1 |
| **Total** | | **~$35-60** |

✅ Covered by your AWS startup credits!

---

## 📊 Expected Results

After processing the full `Biomedical_Knowledgebase.txt`:

- **Nodes**: 15,000 - 30,000
- **Relationships**: 30,000 - 60,000
- **Node Types**: 18 (Disease, Medication, Symptom, etc.)
- **Relationship Types**: 19 (TREATED_BY, HAS_SYMPTOM, etc.)
- **Processing Time**: 30-60 minutes
- **Database Size**: ~200-500 MB
- **RAM Usage**: 2-4 GB

---

## 🎉 What's Next?

Once your knowledge graph is built:

1. **Export for Sharing**:
   ```cypher
   // In Neo4j Browser
   CALL apoc.export.json.all("medical-kb-export.json", {useTypes:true})
   ```

2. **Deploy API** (optional):
   - Use the `medical_kg_api_project/` folder
   - Deploy to AWS Lambda with your API endpoints
   - Query your graph from anywhere

3. **Iterate and Improve**:
   - Add more source documents
   - Refine entity extraction prompts
   - Optimize queries for your use case

---

## 📞 Need Help?

If you get stuck:
1. Check error messages carefully
2. Verify all services are running (Neo4j, PostgreSQL)
3. Test individual components (UMLS connection, AWS credentials)
4. Check the logs for detailed error info

---

## ✅ Quick Checklist

Before running `python run_pipeline.py`:

- [ ] Neo4j Desktop installed and running
- [ ] Database "medical-kb" created with password
- [ ] APOC plugin installed in Neo4j
- [ ] Python dependencies installed (`pip install -r requirements.txt`)
- [ ] AWS credentials configured (`aws configure`)
- [ ] PostgreSQL UMLS database running and tested
- [ ] Source document exists (`Biomedical_Knowledgebase.txt`)

**All checked?** → Run `python run_pipeline.py` and watch the magic happen! 🚀

