# 📦 Requirements Guide

## Two Separate Environments

This project has **two distinct components** with different dependencies:

```
Medical-KB/
├── requirements_pipeline.txt  ← For building knowledge graph (LOCAL)
└── medical_kg_api_project/
    └── requirements_*.txt     ← For deploying API (AWS Lambda)
```

---

## 🔬 **Pipeline Requirements** (What You Need Now)

**Purpose**: Build the knowledge graph on your local machine

**Install**:
```bash
cd C:\Users\achus\Medical-KB
pip install -r requirements_pipeline.txt
```

**What it includes**:
- ✅ `boto3` - AWS Comprehend Medical & Bedrock
- ✅ `psycopg2-binary` - UMLS PostgreSQL connection
- ✅ `neo4j` - Neo4j database driver
- ✅ `sentence-transformers` - Local embeddings (no OpenAI!)
- ✅ `llama-index-core` - Document processing
- ✅ `llama-index-llms-bedrock` - AWS Claude integration
- ❌ NO FastAPI (not needed for pipeline)
- ❌ NO OpenAI packages (using sentence-transformers)
- ❌ NO graph-stores packages (direct Neo4j driver)

**Use with**:
```bash
python run_pipeline.py
```

---

## 🚀 **API Requirements** (For Future Deployment)

**Purpose**: Deploy FastAPI service to query your knowledge graph

**Install** (when deploying API):
```bash
cd medical_kg_api_project
pip install -r requirements_api.txt  # or use existing requirements_*.txt
```

**What it includes**:
- ✅ `fastapi` + `mangum` - API framework & Lambda adapter
- ✅ `openai` - OpenAI API for text-to-Cypher generation
- ✅ `llama-index-*-openai` - OpenAI-based components
- ✅ `llama-index-graph-stores-neo4j` - Graph query integration
- ❌ NO sentence-transformers (using OpenAI embeddings)
- ❌ NO boto3 Comprehend Medical (not needed for queries)

**Use with**:
```bash
# Local testing
uvicorn main:app --reload

# Or deploy to Lambda (see medical_kg_api_project/deploy-*.bat)
```

---

## 🔍 **Why Two Separate Files?**

### **Problem We Had**:
Mixing pipeline + API requirements caused dependency conflicts:
- Pipeline needs `llama-index-core` 0.13+ for Bedrock
- Some API packages wanted `llama-index-core` 0.12.x
- Result: Impossible to resolve! 💥

### **Solution**:
Separate environments:
```
Pipeline Environment (Local)
├── Build knowledge graph
├── Uses AWS Bedrock (via credits)
├── Uses sentence-transformers (local, free)
└── Writes to Neo4j

API Environment (AWS Lambda)  
├── Query knowledge graph
├── Uses OpenAI (for text-to-Cypher)
├── Uses OpenAI embeddings (for semantic search)
└── Reads from Neo4j
```

---

## 🎯 **Quick Commands**

### **For Pipeline Development (NOW)**:
```bash
# Install dependencies
pip install -r requirements_pipeline.txt

# Run the pipeline
python run_pipeline.py

# Test UMLS connection
python test_umls_connection.py
```

### **For API Deployment (LATER)**:
```bash
# Go to API directory
cd medical_kg_api_project

# Use existing requirements
pip install -r requirements_simple.txt

# Test locally
python test_api.py
```

---

## ✅ **Backwards Compatibility**

The old `requirements.txt` now points to `requirements_pipeline.txt`, so:

```bash
# These are equivalent:
pip install -r requirements.txt
pip install -r requirements_pipeline.txt
```

---

## 📊 **Package Count Comparison**

| Category | Pipeline | API |
|----------|----------|-----|
| Total packages | ~15 | ~20 |
| llama-index modules | 2 | 4 |
| Embedding solution | sentence-transformers (local) | OpenAI (cloud) |
| Use case | Build once | Query many times |

---

## 🐛 **Troubleshooting**

### **"Dependency conflict" errors**
**Solution**: Make sure you're using the right requirements file!
```bash
# For pipeline:
pip install -r requirements_pipeline.txt

# NOT the old requirements.txt (if you edited it manually)
```

### **"Module not found" when running pipeline**
**Solution**: 
```bash
pip install -r requirements_pipeline.txt --force-reinstall
```

### **"Module not found" when testing API**
**Solution**:
```bash
cd medical_kg_api_project
pip install -r requirements_simple.txt
```

---

## 💡 **Pro Tip**

Use separate virtual environments:

```bash
# Pipeline environment
python -m venv venv_pipeline
venv_pipeline\Scripts\activate
pip install -r requirements_pipeline.txt

# API environment (later)
python -m venv venv_api
venv_api\Scripts\activate
cd medical_kg_api_project
pip install -r requirements_simple.txt
```

This keeps them completely isolated! 🎯

