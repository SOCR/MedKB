#!/usr/bin/env python3
"""
BioGraph Knowledge Graph Generation Pipeline - Main Execution Script
Processes medical text documents and builds a Neo4j knowledge graph with enrichment.
"""

import os
import sys
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


def main():
    """Main pipeline execution function."""
    print("\n" + "="*60)
    print("🧬 BIOGRAPH KNOWLEDGE GRAPH GENERATION PIPELINE")
    print("="*60 + "\n")
    
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
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("  ✅ Embedding model loaded")
        
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
        # Check if file exists
        if not os.path.exists(SOURCE_DOCUMENT_PATH):
            # Try alternative path
            alt_path = os.path.join("data_corpus", "Biomedical_Knowledgebase.txt")
            if os.path.exists(alt_path):
                SOURCE_DOCUMENT_PATH = alt_path
            else:
                raise FileNotFoundError(f"Source document not found at {SOURCE_DOCUMENT_PATH}")
        
        # Load document
        with open(SOURCE_DOCUMENT_PATH, 'r', encoding='utf-8') as f:
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
        print(f"   Please ensure the source document exists at: {SOURCE_DOCUMENT_PATH}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ FATAL: Error loading document: {e}")
        sys.exit(1)
    
    # ==========================================================================
    # STEP 3: Process Chunks and Build Knowledge Graph
    # ==========================================================================
    print("📋 STEP 3: Processing chunks and building knowledge graph...")
    print("-" * 60)
    print(f"  ⚙️  Processing in batches of 5 chunks")
    print(f"  📊 Total chunks to process: {len(text_nodes)}")
    print()
    
    # For initial testing, process only first 10 chunks
    # Remove this limit once you verify everything works!
    TEST_MODE = True
    if TEST_MODE:
        print("  ⚠️  TEST MODE: Processing only first 10 chunks")
        text_nodes = text_nodes[:10]
        print(f"  📊 Test batch size: {len(text_nodes)} chunks")
        print()
    
    batch_size = 5
    num_batches = (len(text_nodes) + batch_size - 1) // batch_size
    
    total_nodes_loaded = 0
    total_relationships_loaded = 0
    
    try:
        for batch_idx in range(num_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(text_nodes))
            batch_nodes = text_nodes[start_idx:end_idx]
            
            print(f"\n  📦 Batch {batch_idx + 1}/{num_batches} (chunks {start_idx + 1}-{end_idx})")
            print("  " + "-" * 56)
            
            all_enriched_nodes = []
            all_enriched_relationships = []
            
            # Process each chunk in the batch
            for chunk_idx, node in enumerate(batch_nodes, start=start_idx + 1):
                print(f"\n    🔄 Processing chunk {chunk_idx}/{len(text_nodes)}...")
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
    
    if TEST_MODE:
        print(f"\n⚠️  TEST MODE was enabled - only {len(text_nodes)} chunks processed")
        print(f"  To process full document, set TEST_MODE = False in run_pipeline.py")
    
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

