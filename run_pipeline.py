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
from datetime import datetime
from neo4j import GraphDatabase
import boto3
import psycopg2
from sentence_transformers import SentenceTransformer
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter

# Import all functions from utils
from utils import (
    initialize_llm,
    process_text_chunk,
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
# CHECKPOINT FUNCTIONALITY
# =============================================================================
CHECKPOINT_FILE = "pipeline_checkpoint.json"

def save_checkpoint(chunk_index, total_chunks, nodes_loaded, relationships_loaded):
    """Save pipeline progress to checkpoint file."""
    checkpoint = {
        "last_processed_chunk": chunk_index,
        "total_chunks": total_chunks,
        "total_nodes_loaded": nodes_loaded,
        "total_relationships_loaded": relationships_loaded,
        "timestamp": datetime.now().isoformat(),
        "status": "in_progress"
    }
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(checkpoint, f, indent=2)
    print(f"  💾 Checkpoint saved: chunk {chunk_index}/{total_chunks}")

def load_checkpoint():
    """Load checkpoint from file if it exists."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            checkpoint = json.load(f)
        return checkpoint
    return None

def mark_checkpoint_complete(total_nodes, total_relationships):
    """Mark pipeline as complete in checkpoint file."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r') as f:
            checkpoint = json.load(f)
        checkpoint["status"] = "completed"
        checkpoint["completion_time"] = datetime.now().isoformat()
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
    return parser.parse_args()


def main():
    """Main pipeline execution function."""
    # Parse command line arguments
    args = parse_arguments()
    
    print("\n" + "="*60)
    print("🧬 BIOGRAPH KNOWLEDGE GRAPH GENERATION PIPELINE")
    print("="*60 + "\n")
    
    # Handle resume/checkpoint logic
    start_chunk = 0
    checkpoint = None
    
    if args.resume:
        checkpoint = load_checkpoint()
        if checkpoint:
            start_chunk = checkpoint["last_processed_chunk"] + 1
            print(f"📂 Resuming from checkpoint:")
            print(f"   Last processed: Chunk {checkpoint['last_processed_chunk']}")
            print(f"   Nodes loaded so far: {checkpoint['total_nodes_loaded']}")
            print(f"   Relationships loaded so far: {checkpoint['total_relationships_loaded']}")
            print(f"   Timestamp: {checkpoint['timestamp']}")
            print(f"   Starting from chunk: {start_chunk}\n")
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
        
        # 1d. Initialize LLM (AWS Bedrock Claude)
        print("  🔧 Initializing LLM (AWS Bedrock Claude)...")
        llm = initialize_llm()
        
        # 1e. Initialize Embedding Model
        print("  🔧 Loading embedding model (this may take a minute)...")
        # Using all-mpnet-base-v2 for better quality (768d vs 384d)
        # Change to 'all-MiniLM-L6-v2' if you need faster/lighter
        embedding_model = SentenceTransformer('all-mpnet-base-v2')
        print("  ✅ Embedding model loaded (all-mpnet-base-v2, 768 dimensions)")
        
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
    # STEP 2: Load and Chunk Source Document
    # ==========================================================================
    print("📋 STEP 2: Loading and chunking source document...")
    print("-" * 60)
    
    try:
        # Check if file exists at primary location
        doc_path = SOURCE_DOCUMENT_PATH
        if not os.path.exists(doc_path):
            # Try alternative path
            alt_path = os.path.join("data_corpus", "Biomedical_Knowledgebase.txt")
            if os.path.exists(alt_path):
                doc_path = alt_path
                print(f"  📁 Using document from: {alt_path}")
            else:
                raise FileNotFoundError(f"Source document not found at {SOURCE_DOCUMENT_PATH} or {alt_path}")
        
        # Load document
        with open(doc_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        print(f"  📄 Loaded document: {len(text):,} characters")
        
        # Split into chunks
        documents = [Document(text=text)]
        splitter = SentenceSplitter(chunk_size=512, chunk_overlap=20)
        text_nodes = splitter.get_nodes_from_documents(documents)
        
        print(f"  ✂️  Split into {len(text_nodes):,} chunks")
        print(f"  ✅ Ready for processing\n")
        
    except FileNotFoundError as e:
        print(f"\n❌ FATAL: {e}")
        print(f"   Please ensure the source document exists")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ FATAL: Error loading document: {e}")
        sys.exit(1)
    
    # ==========================================================================
    # STEP 3: Process Chunks and Build Knowledge Graph
    # ==========================================================================
    print("📋 STEP 3: Processing chunks and building knowledge graph...")
    print("-" * 60)
    
    # Determine batch size and mode
    batch_size = args.batch_size
    print(f"  ⚙️  Processing in batches of {batch_size} chunks")
    print(f"  📊 Total chunks in document: {len(text_nodes)}")
    
    # Test mode logic
    TEST_MODE = args.test_mode and not args.full_run
    original_chunk_count = len(text_nodes)
    
    if TEST_MODE:
        print("  ⚠️  TEST MODE: Processing only first 10 chunks")
        text_nodes = text_nodes[:10]
        print(f"  📊 Test batch size: {len(text_nodes)} chunks")
    elif args.full_run:
        print(f"  🚀 FULL RUN MODE: Processing all {len(text_nodes)} chunks")
    
    # Skip to start_chunk if resuming
    if start_chunk > 0:
        if start_chunk >= len(text_nodes):
            print(f"\n⚠️  Start chunk ({start_chunk}) >= total chunks ({len(text_nodes)})")
            print("  Nothing to process!")
            sys.exit(0)
        print(f"  ⏩ Skipping to chunk {start_chunk}")
        text_nodes = text_nodes[start_chunk:]
        print(f"  📊 Remaining chunks to process: {len(text_nodes)}")
    print()
    
    num_batches = (len(text_nodes) + batch_size - 1) // batch_size
    
    # Initialize totals (from checkpoint if resuming)
    if checkpoint:
        total_nodes_loaded = checkpoint["total_nodes_loaded"]
        total_relationships_loaded = checkpoint["total_relationships_loaded"]
    else:
        total_nodes_loaded = 0
        total_relationships_loaded = 0
    
    try:
        for batch_idx in range(num_batches):
            batch_start_idx = batch_idx * batch_size
            batch_end_idx = min(batch_start_idx + batch_size, len(text_nodes))
            batch_nodes = text_nodes[batch_start_idx:batch_end_idx]
            
            # Calculate absolute chunk indices (accounting for start_chunk offset)
            abs_start = start_chunk + batch_start_idx
            abs_end = start_chunk + batch_end_idx
            
            print(f"\n  📦 Batch {batch_idx + 1}/{num_batches} (chunks {abs_start + 1}-{abs_end})")
            print("  " + "-" * 56)
            
            all_enriched_nodes = []
            all_enriched_relationships = []
            
            # Process each chunk in the batch
            for local_idx, node in enumerate(batch_nodes):
                abs_chunk_idx = start_chunk + batch_start_idx + local_idx
                print(f"\n    🔄 Processing chunk {abs_chunk_idx + 1}/{original_chunk_count}...")
                text_chunk = node.get_content()
                
                try:
                    # Call the main enrichment pipeline
                    enriched_data = process_text_chunk(
                        text_chunk=text_chunk,
                        llm=llm,
                        aws_client=aws_client,
                        umls_cursor=umls_cursor,
                        embedding_model=embedding_model
                    )
                    
                    all_enriched_nodes.extend(enriched_data['nodes'])
                    all_enriched_relationships.extend(enriched_data['relationships'])
                    
                    print(f"    ✅ Extracted {len(enriched_data['nodes'])} nodes, "
                          f"{len(enriched_data['relationships'])} relationships")
                    
                except Exception as e:
                    print(f"    ⚠️  Error processing chunk {chunk_idx}: {e}")
                    print(f"    ⏭️  Skipping to next chunk...")
                    continue
            
            # Load batch to Neo4j
            if all_enriched_nodes or all_enriched_relationships:
                print(f"\n  💾 Loading batch to Neo4j...")
                print(f"     Nodes: {len(all_enriched_nodes)}")
                print(f"     Relationships: {len(all_enriched_relationships)}")
                
                try:
                    with neo4j_driver.session(database=NEO4J_DATABASE) as session:
                        if all_enriched_nodes:
                            session.execute_write(load_nodes_to_neo4j, all_enriched_nodes)
                            total_nodes_loaded += len(all_enriched_nodes)
                        
                        if all_enriched_relationships:
                            session.execute_write(load_relationships_to_neo4j, all_enriched_relationships)
                            total_relationships_loaded += len(all_enriched_relationships)
                    
                    print(f"  ✅ Batch {batch_idx + 1} loaded successfully!")
                    
                    # Save checkpoint after successful batch
                    save_checkpoint(
                        chunk_index=abs_end - 1,  # Last chunk in this batch
                        total_chunks=original_chunk_count,
                        nodes_loaded=total_nodes_loaded,
                        relationships_loaded=total_relationships_loaded
                    )
                    
                except Exception as e:
                    print(f"  ❌ Error loading batch to Neo4j: {e}")
                    print(f"  ⚠️  Continuing with next batch...")
                    continue
            else:
                print(f"  ⚠️  No data extracted from batch {batch_idx + 1}")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user")
        print("  Partial data may have been loaded to Neo4j")
    except Exception as e:
        print(f"\n❌ Unexpected error during processing: {e}")
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
    
    # Print summary
    print("\n" + "="*60)
    print("🎉 PIPELINE COMPLETED!")
    print("="*60)
    print(f"\n📊 Summary:")
    print(f"  • Total chunks processed: {len(text_nodes)}")
    print(f"  • Nodes loaded: {total_nodes_loaded}")
    print(f"  • Relationships loaded: {total_relationships_loaded}")
    
    # Mark checkpoint as complete
    if start_chunk + len(text_nodes) >= original_chunk_count or not TEST_MODE:
        mark_checkpoint_complete(total_nodes_loaded, total_relationships_loaded)
        print(f"\n✅ Pipeline marked as complete in checkpoint")
    
    if TEST_MODE:
        print(f"\n⚠️  TEST MODE was enabled - only 10 chunks processed")
        print(f"  To process full document, run: python run_pipeline.py --full-run")
    
    print(f"\n💡 Resume options:")
    print(f"  • Resume from checkpoint: python run_pipeline.py --resume")
    print(f"  • Start from specific chunk: python run_pipeline.py --start-chunk N")
    print(f"  • Process all chunks: python run_pipeline.py --full-run")
    
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

