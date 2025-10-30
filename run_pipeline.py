#!/usr/bin/env python3
"""
BioGraph Knowledge Graph Generation Pipeline - Main Execution Script
Processes medical text documents and builds a Neo4j knowledge graph with enrichment.

Supports checkpoint/resume functionality:
  python run_pipeline.py                    # Start from beginning
  python run_pipeline.py --resume           # Resume from last checkpoint
  python run_pipeline.py --start-chunk 100  # Start from specific chunk
"""

import os
import sys
import json
import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path
from neo4j import GraphDatabase
import boto3
import psycopg2
from sentence_transformers import SentenceTransformer
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn, MofNCompleteColumn
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

# Import all functions from utils
from utils import (
    initialize_llm,
    initialize_llm_lmstudio,
    process_text_chunk,
    extract_document_context,
    create_source_node,
    load_nodes_to_neo4j,
    load_relationships_to_neo4j,
    NEO4J_URI,
    NEO4J_USERNAME,
    NEO4J_PASSWORD,
    NEO4J_DATABASE,
    UMLS_DB_NAME,
    UMLS_DB_USER,
    UMLS_DB_PASSWORD,
    UMLS_DB_HOST,
    UMLS_DB_PORT,
    AWS_REGION,
    SOURCE_DOCUMENT_PATH
)

# =============================================================================
# RICH CONSOLE AND PROGRESS
# =============================================================================
console = Console()

def format_time(seconds):
    """Format seconds into human-readable time string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.2f}h"

# =============================================================================
# MULTI-DOCUMENT PROCESSING HELPERS
# =============================================================================

def get_document_list(data_directory):
    """
    Scan directory for text files to process.
    
    Args:
        data_directory: Path to directory containing documents
        
    Returns:
        list: List of Path objects for documents to process
    """
    data_path = Path(data_directory)
    if not data_path.exists():
        return []
    
    # Find all .txt files
    txt_files = list(data_path.glob("*.txt"))
    return sorted(txt_files)  # Sort for consistent ordering


def generate_source_id(file_path):
    """
    Generate unique source ID from file path.
    For PMC files: extract PMC ID from filename
    For other files: use sanitized filename
    
    Args:
        file_path: Path object for the file
        
    Returns:
        str: Unique source identifier
    """
    filename = file_path.stem  # e.g., "PMC8675309" or "sample_text"
    
    # Check if PMC file
    if filename.startswith("PMC"):
        return filename  # Already a good ID
    else:
        # Sanitize filename
        return f"DOC_{filename.replace(' ', '_')}"


def load_document_skip_header(file_path, skip_lines=75):
    """
    Load document text, optionally skipping first N lines.
    Used to skip header that was already processed for context.
    
    Args:
        file_path: Path to the document file
        skip_lines: Number of lines to skip (default: 75)
        
    Returns:
        str: Document text with header removed
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        # Skip header lines
        for _ in range(skip_lines):
            line = f.readline()
            if not line:  # End of file reached
                break
        
        # Read rest of document
        remaining_text = f.read()
    
    return remaining_text

# =============================================================================
# OUTPUT DIRECTORY AND JSON STORAGE
# =============================================================================
OUTPUT_DIR = Path("output")

def ensure_output_directory():
    """Create output directory if it doesn't exist."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    console.print(f"  📁 Output directory: {OUTPUT_DIR.absolute()}")

def save_batch_json(batch_number, chunk_range, nodes, relationships, processing_time):
    """Save batch data to JSON file."""
    import numpy as np
    
    batch_file = OUTPUT_DIR / f"batch_{batch_number:04d}.json"
    
    # Convert numpy arrays to lists for JSON serialization
    def convert_numpy(obj):
        """Recursively convert numpy arrays to lists."""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: convert_numpy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_numpy(item) for item in obj]
        else:
            return obj
    
    # Convert nodes and relationships
    serializable_nodes = convert_numpy(nodes)
    serializable_relationships = convert_numpy(relationships)
    
    batch_data = {
        "batch_number": batch_number,
        "chunk_range": {
            "start": chunk_range[0],
            "end": chunk_range[1]
        },
        "timestamp": datetime.now().isoformat(),
        "processing_time_seconds": round(processing_time, 2),
        "nodes": serializable_nodes,
        "relationships": serializable_relationships,
        "stats": {
            "nodes_count": len(nodes),
            "relationships_count": len(relationships)
        }
    }
    
    with open(batch_file, 'w', encoding='utf-8') as f:
        json.dump(batch_data, f, indent=2, ensure_ascii=False)
    
    return batch_file

def save_pipeline_metadata(total_batches, total_chunks, total_nodes, total_rels, start_time, end_time):
    """Save pipeline summary metadata."""
    metadata_file = OUTPUT_DIR / "pipeline_metadata.json"
    
    duration = end_time - start_time
    
    metadata = {
        "pipeline_version": "1.0",
        "run_info": {
            "total_batches": total_batches,
            "total_chunks_processed": total_chunks,
            "start_time": datetime.fromtimestamp(start_time).isoformat(),
            "end_time": datetime.fromtimestamp(end_time).isoformat(),
            "duration_seconds": round(duration, 2),
            "duration_human": format_time(duration)
        },
        "results": {
            "total_nodes": total_nodes,
            "total_relationships": total_rels,
            "avg_nodes_per_chunk": round(total_nodes / total_chunks, 2) if total_chunks > 0 else 0,
            "avg_relationships_per_chunk": round(total_rels / total_chunks, 2) if total_chunks > 0 else 0
        },
        "output_files": {
            "batch_files_pattern": "batch_####.json",
            "batch_files_count": total_batches,
            "batch_files_location": str(OUTPUT_DIR.absolute())
        }
    }
    
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    return metadata_file

# =============================================================================
# CHECKPOINT FUNCTIONALITY (Multi-Document Support)
# =============================================================================
CHECKPOINT_FILE = "pipeline_checkpoint.json"

def save_checkpoint(doc_index, doc_id, total_docs, chunk_index, total_chunks_in_doc, 
                   completed_docs, nodes_loaded, relationships_loaded):
    """Save pipeline progress with document-level tracking."""
    checkpoint = {
        # Document-level tracking
        "current_document_index": doc_index,
        "current_document_id": doc_id,
        "total_documents": total_docs,
        "completed_documents": completed_docs,
        "documents_processed": len(completed_docs),
        
        # Chunk-level tracking (within current document)
        "last_processed_chunk": chunk_index,
        "total_chunks_in_document": total_chunks_in_doc,
        
        # Global stats
        "total_nodes_loaded": nodes_loaded,
        "total_relationships_loaded": relationships_loaded,
        
        # Timestamps
        "timestamp": datetime.now().isoformat(),
        "status": "in_progress"
    }
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(checkpoint, f, indent=2)

def load_checkpoint():
    """Load checkpoint from file if it exists."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            checkpoint = json.load(f)
        return checkpoint
    return None

def mark_checkpoint_complete(total_docs, total_nodes, total_relationships):
    """Mark pipeline as complete in checkpoint file."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            checkpoint = json.load(f)
        checkpoint["status"] = "completed"
        checkpoint["completion_time"] = datetime.now().isoformat()
        checkpoint["total_documents_processed"] = total_docs
        checkpoint["final_nodes"] = total_nodes
        checkpoint["final_relationships"] = total_relationships
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump(checkpoint, f, indent=2)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='BioGraph Knowledge Graph Generation Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py                    # Start from beginning
  python run_pipeline.py --resume           # Resume from last checkpoint
  python run_pipeline.py --start-chunk 100  # Start from chunk 100
  python run_pipeline.py --test-mode        # Process only 10 chunks (default)
  python run_pipeline.py --full-run         # Process all chunks
        """
    )
    parser.add_argument('--resume', action='store_true',
                       help='Resume from last checkpoint')
    parser.add_argument('--start-chunk', type=int, default=None,
                       help='Start processing from specific chunk number (0-indexed)')
    parser.add_argument('--test-mode', action='store_true', default=True,
                       help='Process only first 10 chunks (default)')
    parser.add_argument('--full-run', action='store_true',
                       help='Process all chunks (override test mode)')
    parser.add_argument('--batch-size', type=int, default=5,
                       help='Number of chunks to process per batch (default: 5)')
    parser.add_argument('--use-lm-studio', action='store_true',
                       help='Use local LM Studio server instead of AWS Bedrock (faster, free)')
    parser.add_argument('--lm-studio-url', type=str, default='http://127.0.0.1:1234/v1',
                       help='LM Studio server URL (default: http://127.0.0.1:1234/v1)')
    parser.add_argument('--data-directory', type=str, default='data_corpus/',
                       help='Directory containing documents to process (default: data_corpus/)')
    parser.add_argument('--single-document', type=str, default=None,
                       help='Process a single document file instead of directory')
    return parser.parse_args()


def main():
    """Main pipeline execution function."""
    # Parse command line arguments
    args = parse_arguments()
    
    print("\n" + "="*60)
    print("🧬 BIOGRAPH KNOWLEDGE GRAPH GENERATION PIPELINE")
    print("="*60 + "\n")
    
    # Handle resume/checkpoint logic
    checkpoint = None
    start_doc_index = 0
    start_chunk = 0
    completed_documents = []
    
    if args.resume:
        checkpoint = load_checkpoint()
        if checkpoint:
            start_doc_index = checkpoint.get("current_document_index", 0)
            start_chunk = checkpoint.get("last_processed_chunk", 0) + 1
            completed_documents = checkpoint.get("completed_documents", [])
            print(f"📂 Resuming from checkpoint:")
            print(f"   Document {start_doc_index + 1} ({checkpoint.get('current_document_id', 'unknown')})")
            print(f"   Last processed: Chunk {checkpoint.get('last_processed_chunk', 0)}")
            print(f"   Documents completed: {len(completed_documents)}")
            print(f"   Nodes loaded so far: {checkpoint['total_nodes_loaded']}")
            print(f"   Relationships loaded so far: {checkpoint['total_relationships_loaded']}")
            print(f"   Timestamp: {checkpoint['timestamp']}")
            print(f"   Resuming from chunk: {start_chunk}\n")
        else:
            print("⚠️  No checkpoint found. Starting from beginning.\n")
    elif args.start_chunk is not None:
        start_chunk = args.start_chunk
        print(f"🎯 Starting from chunk {start_chunk} (user specified)\n")
    
    # ==========================================================================
    # STEP 1: Initialize All Services
    # ==========================================================================
    print("📋 STEP 1: Initializing services...")
    print("-" * 60)
    
    try:
        # 1a. Initialize AWS Comprehend Medical
        print("  🔧 Initializing AWS Comprehend Medical...")
        aws_client = boto3.client('comprehendmedical', region_name=AWS_REGION)
        print("  ✅ AWS Comprehend Medical ready")
        
        # 1b. Initialize UMLS Database Connection
        print("  🔧 Connecting to UMLS PostgreSQL database...")
        umls_conn = psycopg2.connect(
            dbname=UMLS_DB_NAME,
            user=UMLS_DB_USER,
            password=UMLS_DB_PASSWORD,
            host=UMLS_DB_HOST,
            port=UMLS_DB_PORT
        )
        umls_cursor = umls_conn.cursor()
        print("  ✅ UMLS database connected")
        
        # 1c. Initialize Neo4j Graph Database
        print("  🔧 Connecting to Neo4j...")
        neo4j_driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
        )
        neo4j_driver.verify_connectivity()
        print("  ✅ Neo4j database connected")
        
        # 1d. Initialize LLM (AWS Bedrock Claude or LM Studio)
        if args.use_lm_studio:
            print("  🔧 Initializing LLM (LM Studio local server)...")
            llm = initialize_llm_lmstudio(base_url=args.lm_studio_url)
        else:
            print("  🔧 Initializing LLM (AWS Bedrock Claude)...")
            llm = initialize_llm()
        
        # 1e. Initialize Embedding Model
        print("  🔧 Loading embedding model (this may take a minute)...")
        # Using all-mpnet-base-v2 for better quality (768d vs 384d)
        # Change to 'all-MiniLM-L6-v2' if you need faster/lighter
        embedding_model = SentenceTransformer('all-mpnet-base-v2')
        print("  ✅ Embedding model loaded (all-mpnet-base-v2, 768 dimensions)")
        
        # 1f. Create output directory for JSON files
        print("  🔧 Setting up output directory...")
        ensure_output_directory()
        
        print("\n✅ All services initialized successfully!\n")
        
    except Exception as e:
        print(f"\n❌ FATAL: Failed to initialize services")
        print(f"   Error: {e}")
        print("\nPlease check:")
        print("  • Neo4j Desktop is running (bolt://localhost:7687)")
        print("  • PostgreSQL UMLS database is running")
        print("  • AWS credentials are configured (aws configure)")
        print("  • All dependencies are installed (pip install -r requirements.txt)")
        sys.exit(1)
    
    # ==========================================================================
    # STEP 2: Get List of Documents to Process
    # ==========================================================================
    print("📋 STEP 2: Determining documents to process...")
    print("-" * 60)
    
    try:
        # Get list of documents
        if args.single_document:
            document_paths = [Path(args.single_document)]
            if not document_paths[0].exists():
                raise FileNotFoundError(f"Specified document not found: {args.single_document}")
            console.print(f"  📄 Single document mode: {document_paths[0].name}")
        else:
            # Check if data directory exists and has files
            document_paths = get_document_list(args.data_directory)
            if not document_paths:
                console.print(f"  ⚠️  No .txt files found in {args.data_directory}")
                console.print(f"  Trying default document...")
                doc_path = Path(SOURCE_DOCUMENT_PATH)
                if not doc_path.exists():
                    alt_path = Path("data_corpus") / "Biomedical_Knowledgebase.txt"
                    if alt_path.exists():
                        doc_path = alt_path
                    else:
                        raise FileNotFoundError(f"No documents found")
                document_paths = [doc_path]
        
        console.print(f"  📚 Found {len(document_paths)} document(s) to process")
        
        # Filter out completed documents if resuming
        if completed_documents:
            console.print(f"  ✓ {len(completed_documents)} document(s) already completed")
            remaining = []
            for doc_path in document_paths:
                source_id = generate_source_id(doc_path)
                if source_id not in completed_documents:
                    remaining.append(doc_path)
            console.print(f"  → {len(remaining)} document(s) remaining")
            
        console.print()
        
    except FileNotFoundError as e:
        console.print(f"\n❌ FATAL: {e}")
        console.print(f"   Please ensure documents exist in the specified location")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n❌ FATAL: Error scanning documents: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # ==========================================================================
    # STEP 3: Process Each Document
    # ==========================================================================
    print("📋 STEP 3: Processing documents and building knowledge graph...")
    print("-" * 60)
    
    # Batch size configuration
    batch_size = args.batch_size
    TEST_MODE = args.test_mode and not args.full_run
    
    # Initialize global totals (from checkpoint if resuming)
    if checkpoint:
        total_nodes_loaded = checkpoint["total_nodes_loaded"]
        total_relationships_loaded = checkpoint["total_relationships_loaded"]
    else:
        total_nodes_loaded = 0
        total_relationships_loaded = 0
    
    # Start global timing
    pipeline_start_time = time.time()
    
    console.print(f"  ⏱️  Pipeline started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"  📚 Total documents to process: {len(document_paths)}")
    console.print(f"  ⚙️  Batch size: {batch_size} chunks per batch\n")
    
    # ==========================================================================
    # DOCUMENT LOOP: Process each document
    # ==========================================================================
    try:
        for doc_idx in range(start_doc_index, len(document_paths)):
            doc_path = document_paths[doc_idx]
            source_id = generate_source_id(doc_path)
            
            # Skip if already completed
            if source_id in completed_documents:
                console.print(f"✓ Skipping {source_id} (already completed)\n")
                continue
            
            console.print(f"\n{'='*60}")
            console.print(f"📄 Document {doc_idx + 1}/{len(document_paths)}: {doc_path.name}")
            console.print(f"{'='*60}\n")
            
            try:
                # Extract document context (species + metadata) from first 75 lines
                console.print(f"  🔍 Extracting document metadata and species...")
                document_context = extract_document_context(
                    file_path=str(doc_path),
                    source_id=source_id,
                    llm=llm
                )
            
                console.print(f"  ├─ Title: {document_context['title'][:70]}{'...' if len(document_context['title']) > 70 else ''}")
                console.print(f"  ├─ Journal: {document_context['journal']}")
                console.print(f"  ├─ Species: {document_context['primary_species']} ({document_context['species_confidence']})")
                console.print(f"  └─ Study Type: {document_context['study_type']}\n")
                
                # Create Source node in Neo4j
                create_source_node(neo4j_driver, document_context)
                
                # Load document text (skip first 75 lines already processed for context)
                text = load_document_skip_header(doc_path, skip_lines=75)
                console.print(f"  📄 Loaded: {len(text):,} characters (header skipped)")
                
                # Split into chunks
                documents = [Document(text=text)]
                splitter = SentenceSplitter(chunk_size=512, chunk_overlap=20)
                text_nodes = splitter.get_nodes_from_documents(documents)
                
                console.print(f"  ✂️  Split into {len(text_nodes):,} chunks\n")
            
            except Exception as e:
                console.print(f"[red]❌ Error loading document {source_id}: {e}[/red]")
                console.print(f"[yellow]⏭️  Skipping to next document...[/yellow]\n")
                continue
        
            # Test mode logic (per document)
            original_chunk_count = len(text_nodes)
            if TEST_MODE:
                console.print(f"  ⚠️  TEST MODE: Processing only first 10 chunks of this document")
                text_nodes = text_nodes[:10]
            
            # Skip to start_chunk if resuming this specific document
            doc_start_chunk = start_chunk if doc_idx == start_doc_index else 0
            if doc_start_chunk > 0:
                if doc_start_chunk >= len(text_nodes):
                    console.print(f"  ⚠️  Start chunk ({doc_start_chunk}) >= total chunks ({len(text_nodes)})")
                    console.print(f"  Marking document as complete and moving to next...\n")
                    completed_documents.append(source_id)
                    continue
                console.print(f"  ⏩ Resuming from chunk {doc_start_chunk}")
                text_nodes = text_nodes[doc_start_chunk:]
            
            num_batches = (len(text_nodes) + batch_size - 1) // batch_size
            console.print(f"  📊 Processing {len(text_nodes)} chunks in {num_batches} batch(es)\n")
            
            chunk_times = []  # Track chunk times for this document
            
            # Create rich progress bar for this document
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(bar_width=40),
                MofNCompleteColumn(),
                TextColumn("•"),
                TimeElapsedColumn(),
                TextColumn("•"),
                TextColumn("[cyan]{task.fields[speed]}"),
                TextColumn("•"),
                TextColumn("[magenta]ETA: {task.fields[eta]}"),
                TextColumn("•"),
                TextColumn("[green]Nodes: {task.fields[nodes]:,}"),
                TextColumn("•"),
                TextColumn("[yellow]Rels: {task.fields[rels]:,}"),
                console=console,
                expand=False
            )
        
            try:
                with progress:
                    # Add overall progress task with document info
                    doc_name = doc_path.name[:40] + "..." if len(doc_path.name) > 40 else doc_path.name
                    task_id = progress.add_task(
                        f"[bold cyan]Doc {doc_idx + 1}/{len(document_paths)}: {doc_name}",
                        total=len(text_nodes),
                        speed="0.00 it/s",
                        eta="calculating...",
                        nodes=total_nodes_loaded,
                        rels=total_relationships_loaded
                    )
                    
                    for batch_idx in range(num_batches):
                        batch_start_idx = batch_idx * batch_size
                        batch_end_idx = min(batch_start_idx + batch_size, len(text_nodes))
                        batch_nodes = text_nodes[batch_start_idx:batch_end_idx]
                        
                        # Calculate absolute chunk indices (accounting for start_chunk offset)
                        abs_start = start_chunk + batch_start_idx
                        abs_end = start_chunk + batch_end_idx
                        
                        console.print(f"\n  📦 Batch {batch_idx + 1}/{num_batches} (chunks {abs_start + 1}-{abs_end})")
                        console.print("  " + "-" * 56)
                        
                        all_enriched_nodes = []
                        all_enriched_relationships = []
                        
                        # Process each chunk in the batch
                        batch_start_time = time.time()
                        
                        for local_idx, node in enumerate(batch_nodes):
                            abs_chunk_idx = start_chunk + batch_start_idx + local_idx
                            chunk_start_time = time.time()
                            
                            console.log(f"🔄 Processing chunk {abs_chunk_idx + 1}/{original_chunk_count}...")
                            text_chunk = node.get_content()
                            
                            try:
                                # Call the main enrichment pipeline with document context
                                enriched_data = process_text_chunk(
                                    text_chunk=text_chunk,
                                    document_context=document_context,
                                    llm=llm,
                                    aws_client=aws_client,
                                    umls_cursor=umls_cursor,
                                    embedding_model=embedding_model
                                )
                            
                                all_enriched_nodes.extend(enriched_data['nodes'])
                                all_enriched_relationships.extend(enriched_data['relationships'])
                                
                                # Track chunk time
                                chunk_time = time.time() - chunk_start_time
                                chunk_times.append(chunk_time)
                                
                                # Calculate speed and ETA
                                elapsed = time.time() - pipeline_start_time
                                chunks_done = batch_start_idx + local_idx + 1
                                speed = chunks_done / elapsed if elapsed > 0 else 0
                                
                                # Calculate ETA based on average chunk time
                                remaining_chunks = len(text_nodes) - chunks_done
                                avg_time_per_chunk = elapsed / chunks_done if chunks_done > 0 else 0
                                eta_seconds = remaining_chunks * avg_time_per_chunk
                                
                                # Format ETA
                                if eta_seconds > 0:
                                    eta_td = timedelta(seconds=int(eta_seconds))
                                    hours, remainder = divmod(eta_td.seconds, 3600)
                                    minutes, seconds = divmod(remainder, 60)
                                    if eta_td.days > 0:
                                        eta_str = f"{eta_td.days}d {hours:02d}h{minutes:02d}m"
                                    elif hours > 0:
                                        eta_str = f"{hours:02d}h{minutes:02d}m{seconds:02d}s"
                                    else:
                                        eta_str = f"{minutes:02d}m{seconds:02d}s"
                                else:
                                    eta_str = "calculating..."
                                
                                # Update progress (single update with all fields)
                                progress.update(
                                    task_id,
                                    advance=1,
                                    speed=f"{speed:.2f} it/s",
                                    eta=eta_str,
                                    nodes=total_nodes_loaded + len(all_enriched_nodes),
                                    rels=total_relationships_loaded + len(all_enriched_relationships)
                                )
                                
                                console.log(f"✅ Extracted {len(enriched_data['nodes'])} nodes, "
                                        f"{len(enriched_data['relationships'])} rels (⏱️  {chunk_time:.2f}s)")
                                
                            except Exception as e:
                                console.log(f"[yellow]⚠️  Error processing chunk {abs_chunk_idx + 1}: {e}[/yellow]")
                                console.log(f"[yellow]⏭️  Skipping to next chunk...[/yellow]")
                                
                                # Update progress even on error
                                elapsed = time.time() - pipeline_start_time
                                chunks_done = batch_start_idx + local_idx + 1
                                speed = chunks_done / elapsed if elapsed > 0 else 0
                                remaining_chunks = len(text_nodes) - chunks_done
                                avg_time_per_chunk = elapsed / chunks_done if chunks_done > 0 else 0
                                eta_seconds = remaining_chunks * avg_time_per_chunk
                                
                                if eta_seconds > 0:
                                    eta_td = timedelta(seconds=int(eta_seconds))
                                    hours, remainder = divmod(eta_td.seconds, 3600)
                                    minutes, seconds = divmod(remainder, 60)
                                    if eta_td.days > 0:
                                        eta_str = f"{eta_td.days}d {hours:02d}h{minutes:02d}m"
                                    elif hours > 0:
                                        eta_str = f"{hours:02d}h{minutes:02d}m{seconds:02d}s"
                                    else:
                                        eta_str = f"{minutes:02d}m{seconds:02d}s"
                                else:
                                    eta_str = "calculating..."
                                
                                progress.update(task_id, advance=1, speed=f"{speed:.2f} it/s", eta=eta_str)
                                continue
                        
                        # Load batch to Neo4j
                        if all_enriched_nodes or all_enriched_relationships:
                            console.log(f"💾 Loading batch to Neo4j... (Nodes: {len(all_enriched_nodes)}, Rels: {len(all_enriched_relationships)})")
                            
                            try:
                                with neo4j_driver.session(database=NEO4J_DATABASE) as session:
                                    if all_enriched_nodes:
                                        session.execute_write(load_nodes_to_neo4j, all_enriched_nodes)
                                        total_nodes_loaded += len(all_enriched_nodes)
                                    
                                    if all_enriched_relationships:
                                        session.execute_write(load_relationships_to_neo4j, all_enriched_relationships)
                                        total_relationships_loaded += len(all_enriched_relationships)
                                
                                # Update final counts in progress
                                progress.update(
                                    task_id,
                                    nodes=total_nodes_loaded,
                                    rels=total_relationships_loaded
                                )
                                
                                console.log(f"[green]✅ Batch {batch_idx + 1} loaded successfully![/green]")
                                
                                # Calculate batch processing time
                                batch_processing_time = time.time() - batch_start_time
                                
                                # Save checkpoint after successful batch (with document info)
                                # Skip checkpoint saving in test mode to avoid overwriting production checkpoints
                                if not TEST_MODE:
                                    save_checkpoint(
                                        doc_index=doc_idx,
                                        doc_id=source_id,
                                        total_docs=len(document_paths),
                                        chunk_index=abs_end - 1,  # Last chunk in this batch
                                        total_chunks_in_doc=original_chunk_count,
                                        completed_docs=completed_documents,
                                        nodes_loaded=total_nodes_loaded,
                                        relationships_loaded=total_relationships_loaded
                                    )
                                    console.log(f"💾 Checkpoint saved")
                                else:
                                    console.log(f"[dim]⚠️  Test mode: checkpoint not saved[/dim]")
                                
                                # Save batch data to JSON
                                try:
                                    batch_file = save_batch_json(
                                        batch_number=batch_idx + 1,
                                        chunk_range=(abs_start, abs_end - 1),
                                        nodes=all_enriched_nodes,
                                        relationships=all_enriched_relationships,
                                        processing_time=batch_processing_time
                                    )
                                    console.log(f"[cyan]📄 JSON saved: {batch_file.name}[/cyan]")
                                except Exception as json_error:
                                    console.log(f"[yellow]⚠️  JSON save failed: {json_error}[/yellow]")
                                    console.log(f"[yellow]   Data is in Neo4j, JSON backup not created for this batch[/yellow]")
                                
                            except Exception as e:
                                console.log(f"[red]❌ Error loading batch to Neo4j: {e}[/red]")
                                console.log(f"[yellow]⚠️  Continuing with next batch...[/yellow]")
                                continue
                        else:
                            console.log(f"[yellow]⚠️  No data extracted from batch {batch_idx + 1}[/yellow]")
            
            except Exception as e:
                console.print(f"[red]❌ Error during batch processing for document {source_id}: {e}[/red]")
                console.print(f"[yellow]⏭️  Skipping to next document...[/yellow]\n")
                import traceback
                traceback.print_exc()
                continue
            
            # Document processing complete - mark as done
            completed_documents.append(source_id)
            console.print(f"\n[green]✅ Document {source_id} completed successfully![/green]")
            console.print(f"   Nodes: {total_nodes_loaded:,} | Relationships: {total_relationships_loaded:,}\n")
            
            # Reset start_chunk for next document
            start_chunk = 0
    
    # End of document loop
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user (Ctrl+C)")
        elapsed = time.time() - pipeline_start_time
        print(f"  ⏱️  Time elapsed before interrupt: {format_time(elapsed)}")
        print(f"  📦 Partial data loaded: {total_nodes_loaded:,} nodes, {total_relationships_loaded:,} relationships")
        print(f"  💾 Last checkpoint saved - you can resume with: python run_pipeline.py --resume")
    except Exception as e:
        print(f"\n❌ Unexpected error during processing: {e}")
        elapsed = time.time() - pipeline_start_time
        print(f"  ⏱️  Time elapsed before error: {format_time(elapsed)}")
        import traceback
        traceback.print_exc()
    
    # ==========================================================================
    # STEP 4: Cleanup and Summary
    # ==========================================================================
    print("\n" + "="*60)
    print("📋 STEP 4: Cleanup and Summary")
    print("="*60)
    
    # Close connections
    print("  🔧 Closing database connections...")
    if 'umls_conn' in locals():
        umls_conn.close()
        print("  ✅ UMLS connection closed")
    
    if 'neo4j_driver' in locals():
        neo4j_driver.close()
        print("  ✅ Neo4j connection closed")
    
    # Calculate final timing statistics
    total_elapsed = time.time() - pipeline_start_time
    
    # Print summary
    print("\n" + "="*60)
    print("🎉 PIPELINE COMPLETED!")
    print("="*60)
    
    print(f"\n📊 Processing Summary:")
    print(f"  • Total documents processed: {len(completed_documents)}/{len(document_paths)}")
    print(f"  • Nodes loaded: {total_nodes_loaded:,}")
    print(f"  • Relationships loaded: {total_relationships_loaded:,}")
    
    print(f"\n⏱️  Timing Statistics:")
    print(f"  • Total time: {format_time(total_elapsed)}")
    print(f"  • Start: {datetime.fromtimestamp(pipeline_start_time).strftime('%H:%M:%S')}")
    print(f"  • End: {datetime.now().strftime('%H:%M:%S')}")
    
    if total_nodes_loaded > 0 and total_elapsed > 0:
        nodes_per_sec = total_nodes_loaded / total_elapsed
        rels_per_sec = total_relationships_loaded / total_elapsed
        docs_per_hour = (len(completed_documents) / total_elapsed) * 3600 if total_elapsed > 0 else 0
        print(f"  • Throughput: {nodes_per_sec:.1f} nodes/s, {rels_per_sec:.1f} rels/s")
        print(f"  • Processing speed: {docs_per_hour:.1f} documents/hour")
    
    # Save final pipeline metadata
    print(f"\n📄 Saving pipeline metadata...")
    try:
        metadata_file = OUTPUT_DIR / "pipeline_metadata.json"
        metadata = {
            "documents_processed": len(completed_documents),
            "total_documents": len(document_paths),
            "total_nodes": total_nodes_loaded,
            "total_relationships": total_relationships_loaded,
            "duration_seconds": round(total_elapsed, 2),
            "start_time": datetime.fromtimestamp(pipeline_start_time).isoformat(),
            "end_time": datetime.now().isoformat()
        }
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"  ✅ Metadata saved: {metadata_file}")
    except Exception as e:
        print(f"  ⚠️  Could not save metadata: {e}")
    
    # Mark checkpoint as complete
    mark_checkpoint_complete(
        total_docs=len(completed_documents),
        total_nodes=total_nodes_loaded,
        total_relationships=total_relationships_loaded
    )
    print(f"\n✅ Pipeline marked as complete in checkpoint")
    
    if TEST_MODE:
        print(f"\n⚠️  TEST MODE was enabled - only 10 chunks per document")
        print(f"  To process full documents, run: python run_pipeline.py --full-run")
    
    print(f"\n💡 Usage options:")
    print(f"  • Resume from checkpoint: python run_pipeline.py --resume")
    print(f"  • Process specific document: python run_pipeline.py --single-document path/to/file.txt")
    print(f"  • Process all documents: python run_pipeline.py --full-run")
    
    print(f"\n📂 Output Files:")
    print(f"  • JSON batches: {OUTPUT_DIR.absolute()}")
    print(f"  • Completed documents: {len(completed_documents)}")
    print(f"  • Metadata: pipeline_metadata.json")
    
    print(f"\n✅ Access your graph at: http://localhost:7474")
    print(f"   Username: neo4j")
    print(f"   Password: {NEO4J_PASSWORD}")
    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    # Add some nice spacing
    print("\n" * 2)
    
    try:
        main()
    except Exception as e:
        print(f"\n❌ Pipeline failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

