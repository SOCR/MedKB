# 🎨 Rich Progress Bar Features

## Overview
The pipeline now uses the **`rich`** library to provide beautiful, persistent progress bars with real-time statistics while keeping all logs visible!

---

## 🌟 What You'll See

### **Progress Bar (Bottom of Screen)**
```
⠋ Processing chunks... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 5/10 • 00:02:30 • 0.03 it/s • 00:05:00 • Nodes: 45 • Rels: 87
```

**Components**:
- **Spinner** (⠋): Animated to show activity
- **Progress Bar**: Visual representation of completion
- **5/10**: Chunks completed / Total chunks
- **00:02:30**: Time elapsed
- **0.03 it/s**: Processing speed (iterations per second)
- **00:05:00**: Estimated time remaining (ETA)
- **Nodes: 45**: Total nodes extracted so far
- **Rels: 87**: Total relationships extracted so far

### **Logs (Above Progress Bar)**
```
[12:30:45] 🔄 Processing chunk 1/2000...
[12:31:02] ✅ Extracted 8 nodes, 12 rels (⏱️  17.23s)
[12:31:05] 🔄 Processing chunk 2/2000...
[12:31:22] ✅ Extracted 6 nodes, 9 rels (⏱️  16.95s)
[12:31:25] 💾 Loading batch to Neo4j... (Nodes: 14, Rels: 21)
[12:31:27] ✅ Batch 1 loaded successfully!
[12:31:27] 💾 Checkpoint saved
```

**Features**:
- **Timestamps**: Each log entry shows exact time
- **Colored Output**: Success (green), warnings (yellow), errors (red)
- **Scrollable**: Logs scroll up as new ones appear
- **Progress bar stays at bottom**: Never gets pushed up

---

## 🎯 Benefits Over Plain Print

### **Before (Plain Print)**:
```
Processing chunk 1/2000...
Extracted 8 nodes, 12 relationships (17.23s)
Processing chunk 2/2000...
Extracted 6 nodes, 9 relationships (16.95s)
...
[Progress info mixed with logs, hard to track]
```

### **After (Rich Progress)**:
```
[Logs scroll above]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2/2000 • 00:00:34 • 0.06 it/s • 09:12:00 • Nodes: 14 • Rels: 21
[Progress bar stays fixed at bottom]
```

---

## 📊 Real-Time Metrics

### **Speed Tracking**
- **it/s** (iterations per second): How many chunks processed per second
- Updates in real-time as pipeline runs
- Example: `0.03 it/s` = ~2 chunks per minute

### **ETA (Estimated Time Remaining)**
- Calculated based on average chunk processing time
- Example: `09:12:00` = 9 hours, 12 minutes remaining
- Updates dynamically as speed changes

### **Cumulative Counts**
- **Nodes**: Total nodes extracted and loaded so far
- **Rels**: Total relationships extracted and loaded
- Updates after each chunk

---

## 🎨 Color Coding

### **Console Logs**:
- ✅ **Green**: Success messages (batch loaded, checkpoint saved)
- ⚠️ **Yellow**: Warnings (skipped chunks, no data)
- ❌ **Red**: Errors (Neo4j errors, processing failures)
- 🔄 **Blue**: Info (processing status)
- 💾 **Cyan**: Checkpoints and saves

### **Progress Bar**:
- **Cyan**: Task description
- **Blue**: Progress bar itself
- **Green**: Node counts
- **Yellow**: Relationship counts

---

## 💡 Usage Tips

### **1. Watch the Progress Bar**
The progress bar gives you instant feedback:
- **Speed** (it/s): Is it consistent? Slowing down?
- **ETA**: When will it finish?
- **Counts**: Are nodes/rels being extracted?

### **2. Review Logs for Details**
Logs provide detailed information:
- Which chunk is being processed
- How long each chunk takes
- Any errors or warnings
- Checkpoint confirmations

### **3. Terminal Size**
- Works best with wide terminal (120+ columns)
- If too narrow, some metrics may wrap
- Still functional in any terminal size

### **4. Scroll Back**
- You can scroll up to see older logs
- Progress bar stays visible at bottom
- Use terminal's scroll buffer

---

## 🚀 Example Run

Here's what you'll see when running:

```bash
$ python run_pipeline.py

🧬 BIOGRAPH KNOWLEDGE GRAPH GENERATION PIPELINE
============================================================

📋 STEP 1: Initializing services...
  ✅ AWS Comprehend Medical ready
  ✅ UMLS database connected
  ✅ Neo4j database connected
  ✅ AWS Bedrock LLM (Claude 3.7 Sonnet) initialized successfully
  ✅ Embedding model loaded

📋 STEP 2: Loading and chunking source document...
  📄 Loaded document: 523,456 characters
  ✂️  Split into 2,048 chunks
  ✅ Ready for processing

📋 STEP 3: Processing chunks and building knowledge graph...
  ⚙️  Processing in batches of 5 chunks
  📊 Total chunks in document: 2048
  ⚠️  TEST MODE: Processing only first 10 chunks
  ⏱️  Pipeline started at: 2025-01-28 14:32:15

  📦 Batch 1/2 (chunks 1-5)
  --------------------------------------------------------
[14:32:16] 🔄 Processing chunk 1/10...
[14:32:33] ✅ Extracted 8 nodes, 12 rels (⏱️  17.23s)
[14:32:34] 🔄 Processing chunk 2/10...
[14:32:51] ✅ Extracted 6 nodes, 9 rels (⏱️  16.95s)
[14:32:52] 🔄 Processing chunk 3/10...
[14:33:09] ✅ Extracted 7 nodes, 11 rels (⏱️  17.12s)
[14:33:10] 🔄 Processing chunk 4/10...
[14:33:27] ✅ Extracted 9 nodes, 14 rels (⏱️  17.45s)
[14:33:28] 🔄 Processing chunk 5/10...
[14:33:45] ✅ Extracted 5 nodes, 8 rels (⏱️  16.88s)
[14:33:46] 💾 Loading batch to Neo4j... (Nodes: 35, Rels: 54)
[14:33:48] ✅ Batch 1 loaded successfully!
[14:33:48] 💾 Checkpoint saved

⠋ Processing chunks... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 5/10 • 00:01:32 • 0.05 it/s • 00:01:30 • Nodes: 35 • Rels: 54
```

**Bottom Line (Progress Bar)**:
- 5 out of 10 chunks done
- 1 minute 32 seconds elapsed
- Processing at 0.05 chunks/second (~3 chunks/minute)
- About 1 minute 30 seconds remaining
- 35 nodes and 54 relationships loaded so far

---

## 🔧 Technical Details

### **Rich Library Components Used**:

1. **Progress**: Main progress tracking
   - `SpinnerColumn()`: Animated spinner
   - `BarColumn(bar_width=40)`: Visual progress bar
   - `MofNCompleteColumn()`: "M of N" completion text
   - `TimeElapsedColumn()`: Time elapsed
   - `TimeRemainingColumn()`: Estimated time remaining
   - `TextColumn()`: Custom metrics (speed, nodes, rels)

2. **Console**: For logging
   - `console.log()`: Timestamped logs above progress bar
   - `console.print()`: Regular output
   - Supports markdown formatting and colors

3. **Live Display**: Keeps progress bar at bottom while logs scroll

### **Update Frequency**:
- Progress bar: Updates after every chunk
- Speed calculation: Recalculated after every chunk
- ETA: Recalculated based on running average
- Node/Rel counts: Updated after each batch loads

---

## 🎯 Key Improvements

| Feature | Before | After |
|---------|--------|-------|
| **Progress visibility** | Mixed with logs | Fixed at bottom |
| **Speed tracking** | Manual calculation | Real-time it/s |
| **ETA** | Rough estimate | Dynamic calculation |
| **Logs** | Plain text | Colored, timestamped |
| **Visual feedback** | None | Animated spinner + bar |
| **Metrics** | Buried in text | Always visible |
| **User experience** | Hard to track | Professional, clear |

---

## 📝 Notes

### **Performance**:
- Rich adds negligible overhead (~0.01s per update)
- Terminal rendering is fast and efficient
- No impact on actual processing speed

### **Compatibility**:
- Works on Windows, macOS, Linux
- Works in any terminal that supports ANSI colors
- Gracefully degrades in basic terminals

### **Interruption Handling**:
- Ctrl+C still works
- Progress bar stops cleanly
- Final stats shown after interruption

---

## 🎉 Summary

**Rich progress bar gives you**:
- ✅ Real-time progress visualization
- ✅ Instant performance metrics (it/s, ETA)
- ✅ Clean separation of logs and progress
- ✅ Professional, training-framework-like interface
- ✅ Better insight into pipeline performance
- ✅ Easier to monitor long-running jobs

**Perfect for**:
- Long full runs (2000+ chunks)
- Monitoring performance bottlenecks
- Knowing when pipeline will finish
- Professional presentation

---

**Ready to see it in action!** 🚀

Run: `python run_pipeline.py`

