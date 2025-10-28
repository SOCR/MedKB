# 🔄 Checkpoint & Resume Guide

## Overview

The pipeline now supports **checkpoint/resume functionality** so you can stop and restart processing without losing progress!

---

## 🚀 **Usage Examples**

### **1. Start from Beginning (Test Mode)**
```bash
python run_pipeline.py
```
- Processes first **10 chunks** (test mode)
- Saves checkpoint after each batch
- Creates `pipeline_checkpoint.json`

---

### **2. Resume from Last Checkpoint**
```bash
python run_pipeline.py --resume
```
- Reads `pipeline_checkpoint.json`
- Continues from where you left off
- Preserves node/relationship counts

**Example Output**:
```
📂 Resuming from checkpoint:
   Last processed: Chunk 9
   Nodes loaded so far: 45
   Relationships loaded so far: 87
   Timestamp: 2025-01-28T14:30:22
   Starting from chunk: 10
```

---

### **3. Start from Specific Chunk**
```bash
python run_pipeline.py --start-chunk 100
```
- Skips first 100 chunks
- Starts processing from chunk 100
- Useful if you know where failure occurred

---

### **4. Full Run (All Chunks)**
```bash
python run_pipeline.py --full-run
```
- Processes **entire document** (all ~2000 chunks)
- Saves checkpoint after each batch
- Can be resumed if interrupted

---

### **5. Custom Batch Size**
```bash
python run_pipeline.py --batch-size 10
```
- Process 10 chunks per batch instead of 5
- Saves checkpoint after each batch
- Larger batches = fewer checkpoints but more risk

---

### **6. Full Run with Resume**
```bash
# Start full run
python run_pipeline.py --full-run

# If interrupted (Ctrl+C or crash), resume with:
python run_pipeline.py --resume --full-run
```

---

## 📁 **Checkpoint File**

### **Location**: `pipeline_checkpoint.json`

### **Contents**:
```json
{
  "last_processed_chunk": 9,
  "total_chunks": 2000,
  "total_nodes_loaded": 234,
  "total_relationships_loaded": 456,
  "timestamp": "2025-01-28T14:30:22.123456",
  "status": "in_progress"
}
```

### **Fields**:
- `last_processed_chunk`: Last successfully processed chunk (0-indexed)
- `total_chunks`: Total chunks in document
- `total_nodes_loaded`: Cumulative nodes loaded so far
- `total_relationships_loaded`: Cumulative relationships loaded
- `timestamp`: When checkpoint was saved
- `status`: `in_progress` or `completed`

---

## 🛠️ **Common Scenarios**

### **Scenario 1: Pipeline Crashes Mid-Run**

```bash
# You were running:
python run_pipeline.py --full-run

# It crashed at chunk 523
# Resume with:
python run_pipeline.py --resume --full-run
```

**What happens**:
- Reads checkpoint file
- Sees last processed chunk: 522
- Starts from chunk 523
- Preserves node/relationship counts

---

### **Scenario 2: Need to Stop Early**

```bash
# You're running full pipeline
python run_pipeline.py --full-run

# Press Ctrl+C to stop

# Later, resume:
python run_pipeline.py --resume --full-run
```

**Result**: Continues from last checkpoint (saved after each batch)

---

### **Scenario 3: Test Different Starting Points**

```bash
# Test chunks 0-10
python run_pipeline.py

# Test chunks 100-110
python run_pipeline.py --start-chunk 100

# Test chunks 500-510
python run_pipeline.py --start-chunk 500
```

---

### **Scenario 4: Incremental Processing**

```bash
# Day 1: Process first 100 chunks
python run_pipeline.py --start-chunk 0 --full-run
# (Stop after ~20 batches)

# Day 2: Continue
python run_pipeline.py --resume --full-run

# Day 3: Continue again
python run_pipeline.py --resume --full-run
```

---

## ⚠️ **Important Notes**

### **1. Checkpoint Frequency**
- Checkpoints save **after each batch** (default: every 5 chunks)
- If crash occurs mid-batch, that batch will be re-processed
- Use `--batch-size 1` for most frequent checkpoints (slower)

### **2. Duplicate Node Handling**
- Neo4j uses `MERGE` (idempotent operations)
- Re-processing the same chunk won't create duplicates
- Safe to restart from any point

### **3. Checkpoint File Location**
- Saved in current directory: `pipeline_checkpoint.json`
- Don't delete this file if you want to resume!
- Can manually edit to adjust starting point

### **4. Resume Logic**
- `--resume` always uses checkpoint file
- `--start-chunk` overrides checkpoint
- If no checkpoint exists, starts from beginning

---

## 🔍 **Monitoring Progress**

### **View Current Checkpoint**:
```bash
# On Windows:
type pipeline_checkpoint.json

# On Linux/Mac:
cat pipeline_checkpoint.json
```

### **Check Progress in Neo4j**:
```cypher
// Count nodes loaded so far
MATCH (n)
RETURN count(n) as total_nodes

// Count relationships
MATCH ()-[r]->()
RETURN count(r) as total_relationships

// View node types
MATCH (n)
RETURN labels(n)[0] as type, count(*) as count
ORDER BY count DESC
```

---

## 💡 **Best Practices**

### **For Long Runs (Full Document)**:
```bash
# 1. Use screen/tmux (Linux) or run in background
python run_pipeline.py --full-run > pipeline.log 2>&1 &

# 2. Or use smaller batches for more checkpoints
python run_pipeline.py --full-run --batch-size 3
```

### **For Testing**:
```bash
# Test first 10 chunks (default)
python run_pipeline.py

# Test specific section
python run_pipeline.py --start-chunk 500 --test-mode

# Test different batch sizes
python run_pipeline.py --batch-size 10
```

### **For Production**:
```bash
# Full run with optimal batch size
python run_pipeline.py --full-run --batch-size 10

# If it fails, resume:
python run_pipeline.py --resume --full-run --batch-size 10
```

---

## 🐛 **Troubleshooting**

### **Problem**: "No checkpoint found"
```bash
# If you deleted the checkpoint file
# Start fresh:
python run_pipeline.py --start-chunk 0 --full-run
```

### **Problem**: "Start chunk >= total chunks"
```bash
# Your checkpoint is beyond the document
# Either start over or adjust checkpoint manually
# Delete checkpoint and start fresh:
rm pipeline_checkpoint.json
python run_pipeline.py --full-run
```

### **Problem**: Want to restart from scratch
```bash
# Delete checkpoint file
rm pipeline_checkpoint.json  # Linux/Mac
del pipeline_checkpoint.json  # Windows

# Start fresh
python run_pipeline.py --full-run
```

### **Problem**: Checkpoint seems stuck
```bash
# Manually set starting point
python run_pipeline.py --start-chunk 100 --full-run

# This ignores old checkpoint and starts from chunk 100
```

---

## 📊 **Command Reference**

| Command | Description |
|---------|-------------|
| `python run_pipeline.py` | Test mode (10 chunks) |
| `python run_pipeline.py --full-run` | Process all chunks |
| `python run_pipeline.py --resume` | Resume from checkpoint |
| `python run_pipeline.py --start-chunk N` | Start from chunk N |
| `python run_pipeline.py --batch-size N` | Set batch size |
| `python run_pipeline.py --help` | Show all options |

---

## 🎯 **Quick Reference**

### **Common Commands**:
```bash
# Test run
python run_pipeline.py

# Full run
python run_pipeline.py --full-run

# Resume
python run_pipeline.py --resume --full-run

# Start from specific chunk
python run_pipeline.py --start-chunk 500 --full-run

# Custom batch size
python run_pipeline.py --full-run --batch-size 10
```

### **Check Status**:
```bash
# View checkpoint
cat pipeline_checkpoint.json

# Count nodes in Neo4j
# Open Neo4j Browser: http://localhost:7474
# Run: MATCH (n) RETURN count(n)
```

---

**Ready to process with checkpoints!** 🚀

Start with: `python run_pipeline.py` to test, then use `--full-run` when ready!

