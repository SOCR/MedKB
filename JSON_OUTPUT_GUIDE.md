# 📄 JSON Output Guide

## Overview
The pipeline now saves all extracted data to **JSON files** in addition to loading to Neo4j. This provides a portable, human-readable backup and enables data sharing.

---

## 📂 Output Structure

```
Medical-KB/
├── output/
│   ├── batch_0001.json  (chunks 1-5: 35 nodes, 54 rels)
│   ├── batch_0002.json  (chunks 6-10: 28 nodes, 42 rels)
│   ├── batch_0003.json  (chunks 11-15: 41 nodes, 63 rels)
│   ├── ...
│   ├── batch_0400.json  (chunks 1996-2000: 33 nodes, 51 rels)
│   └── pipeline_metadata.json  (summary of entire run)
```

---

## 📝 Batch File Format

Each `batch_####.json` contains:

```json
{
  "batch_number": 1,
  "chunk_range": {
    "start": 0,
    "end": 4
  },
  "timestamp": "2025-01-28T13:45:22.123456",
  "processing_time_seconds": 92.34,
  "nodes": [
    {
      "id": "SNOMED:38341003",
      "name": "Hypertension",
      "labels": ["Disease"],
      "description": "A condition characterized by elevated blood pressure...",
      "synonyms": ["High Blood Pressure", "HTN", "Arterial Hypertension"],
      "standard_code": "SNOMED:38341003",
      "ontology": "SNOMED",
      "confidence": 0.98,
      "source": "primary snomed",
      "embedding": [0.234, -0.456, 0.678, ...]
    },
    ...
  ],
  "relationships": [
    {
      "source_id": "SNOMED:38341003",
      "target_id": "RXNORM:314076",
      "type": "TREATED_BY",
      "description": "Lisinopril is commonly prescribed to manage hypertension"
    },
    ...
  ],
  "stats": {
    "nodes_count": 35,
    "relationships_count": 54
  }
}
```

---

## 📊 Pipeline Metadata Format

`pipeline_metadata.json` contains summary:

```json
{
  "pipeline_version": "1.0",
  "run_info": {
    "total_batches": 400,
    "total_chunks_processed": 2000,
    "start_time": "2025-01-28T10:00:00.123456",
    "end_time": "2025-01-28T20:15:30.654321",
    "duration_seconds": 36930.53,
    "duration_human": "10.26h"
  },
  "results": {
    "total_nodes": 15234,
    "total_relationships": 28945,
    "avg_nodes_per_chunk": 7.62,
    "avg_relationships_per_chunk": 14.47
  },
  "output_files": {
    "batch_files_pattern": "batch_####.json",
    "batch_files_count": 400,
    "batch_files_location": "C:\\Users\\achus\\Medical-KB\\output"
  }
}
```

---

## 🔧 Use Cases

### **1. Backup & Archive**
```bash
# Zip all output files
tar -czf knowledge_graph_backup.tar.gz output/

# Or on Windows
powershell Compress-Archive -Path output\ -DestinationPath knowledge_graph_backup.zip
```

### **2. Data Sharing**
Share specific batches or entire dataset:
```bash
# Share just first 100 batches
cp output/batch_00{01..99}.json shared_data/
cp output/batch_0100.json shared_data/
cp output/pipeline_metadata.json shared_data/
```

### **3. Data Analysis**
```python
import json

# Load a batch
with open('output/batch_0001.json') as f:
    batch = json.load(f)

# Analyze
print(f"Nodes: {len(batch['nodes'])}")
print(f"Relationships: {len(batch['relationships'])}")

# Extract all disease nodes
diseases = [n for n in batch['nodes'] if 'Disease' in n['labels']]
print(f"Diseases: {len(diseases)}")
```

### **4. Import to Different Database**
Use JSON files to load into:
- Another Neo4j instance
- Different graph database (e.g., ArangoDB, OrientDB)
- Document database (e.g., MongoDB, Elasticsearch)
- Data warehouse (e.g., BigQuery, Snowflake)

### **5. Inspect Specific Batches**
```bash
# Pretty print a batch
cat output/batch_0001.json | jq .

# Count nodes in batch
cat output/batch_0001.json | jq '.nodes | length'

# Get all node types
cat output/batch_0001.json | jq '.nodes[].labels[]' | sort | uniq
```

---

## 🔄 Merge Utility

### **Combine All Batches**

```bash
python merge_batches.py
```

**Output**: `merged_output.json` (single file with all data)

### **Options**:
```bash
# Custom output file
python merge_batches.py --output complete_kg.json

# Pretty print (easier to read, but larger file)
python merge_batches.py --pretty

# Different input directory
python merge_batches.py --dir output2
```

### **Merged File Format**:
```json
{
  "metadata": {
    "merged_at": "2025-01-28T21:00:00",
    "source_directory": "C:\\Users\\achus\\Medical-KB\\output",
    "total_batches_merged": 400,
    "pipeline_start": "2025-01-28T10:00:00",
    "pipeline_end": "2025-01-28T20:15:30",
    "total_processing_time_seconds": 36930.53
  },
  "statistics": {
    "total_nodes": 14823,  // After deduplication
    "total_relationships": 28456,  // After deduplication
    "duplicates_removed": {
      "nodes": 411,
      "relationships": 489
    }
  },
  "batch_summary": [
    {"batch_number": 1, "chunk_range": {...}, "nodes_count": 35, "relationships_count": 54},
    ...
  ],
  "nodes": [...],  // All nodes
  "relationships": [...]  // All relationships
}
```

---

## 💡 Benefits

### **1. Safety**
- ✅ Data preserved even if Neo4j crashes
- ✅ Can rebuild graph from JSON
- ✅ Backup before destructive operations

### **2. Portability**
- ✅ Share with collaborators
- ✅ Load into different systems
- ✅ Archive for long-term storage

### **3. Analysis**
- ✅ Easy to inspect with standard tools (jq, Python)
- ✅ Can analyze without running Neo4j
- ✅ Process with data science tools (Pandas, etc.)

### **4. Debugging**
- ✅ Review specific batches
- ✅ Identify problematic chunks
- ✅ Compare different runs

### **5. Resume-Friendly**
- ✅ JSON saved at same time as checkpoint
- ✅ Matches batch granularity
- ✅ No data loss on resume

---

## 📊 File Sizes

**Typical sizes** (with embeddings):
- Single batch: 100-500 KB
- 400 batches: 40-200 MB
- Merged file: 50-250 MB (after deduplication)

**Without embeddings**:
- Single batch: 10-50 KB
- 400 batches: 4-20 MB
- Merged file: 5-25 MB

---

## 🔍 Inspection Examples

### **View Batch Summary**:
```bash
# Using jq
cat output/batch_0001.json | jq '{batch: .batch_number, chunks: .chunk_range, nodes: .stats.nodes_count, rels: .stats.relationships_count, time: .processing_time_seconds}'

# Output:
# {
#   "batch": 1,
#   "chunks": {"start": 0, "end": 4},
#   "nodes": 35,
#   "rels": 54,
#   "time": 92.34
# }
```

### **Find All Medications**:
```bash
cat output/batch_*.json | jq '.nodes[] | select(.labels[] == "Medication") | .name'
```

### **Count Relationship Types**:
```bash
cat output/batch_0001.json | jq '.relationships[].type' | sort | uniq -c
```

### **Python Analysis**:
```python
import json
from pathlib import Path

# Load all batches
batches = []
for file in sorted(Path('output').glob('batch_*.json')):
    with open(file) as f:
        batches.append(json.load(f))

# Aggregate statistics
total_nodes = sum(b['stats']['nodes_count'] for b in batches)
total_rels = sum(b['stats']['relationships_count'] for b in batches)
total_time = sum(b['processing_time_seconds'] for b in batches)

print(f"Total nodes: {total_nodes:,}")
print(f"Total relationships: {total_rels:,}")
print(f"Total time: {total_time/3600:.2f} hours")
print(f"Avg time/batch: {total_time/len(batches):.2f}s")
```

---

## 🚫 Git Ignore

The `output/` directory is automatically ignored by git (in `.gitignore`).

**Reason**: 
- Files are large (40-200 MB)
- Contain processed data (can regenerate)
- May contain sensitive medical information

**To share**: Use zip/tar or upload to cloud storage.

---

## 🎯 Best Practices

1. **Backup regularly**: Copy `output/` to cloud storage after long runs
2. **Merge after completion**: Create single file for easier sharing
3. **Keep metadata**: Always include `pipeline_metadata.json` with batches
4. **Document versions**: Note pipeline version when sharing data
5. **Verify integrity**: Check file sizes and counts match expected values

---

## 🔄 Rebuilding Neo4j from JSON

If you need to rebuild your Neo4j database from JSON:

```python
import json
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

# Load merged file
with open('merged_output.json') as f:
    data = json.load(f)

# Load nodes
with driver.session() as session:
    for node in data['nodes']:
        session.run("""
            MERGE (n {id: $id})
            SET n += $properties
        """, id=node['id'], properties=node)

# Load relationships
with driver.session() as session:
    for rel in data['relationships']:
        session.run("""
            MATCH (source {id: $source_id})
            MATCH (target {id: $target_id})
            MERGE (source)-[r:%s]->(target)
            SET r += $properties
        """ % rel['type'],
            source_id=rel['source_id'],
            target_id=rel['target_id'],
            properties={k:v for k,v in rel.items() if k not in ['source_id', 'target_id', 'type']}
        )
```

---

**JSON output provides flexibility and safety!** 📄✨

Always keep your JSON files as a backup of your knowledge graph data.

