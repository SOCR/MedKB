#!/usr/bin/env python3
"""
Merge Batch JSON Files Utility
Combines all batch_####.json files from output/ directory into a single JSON file.

Usage:
    python merge_batches.py                    # Creates merged_output.json
    python merge_batches.py --output my.json   # Custom output file
    python merge_batches.py --pretty           # Pretty print with indentation
"""

import json
import argparse
from pathlib import Path
from datetime import datetime


def merge_batch_files(output_dir="output", output_file="merged_output.json", pretty=False):
    """Merge all batch JSON files into one."""
    
    output_path = Path(output_dir)
    
    if not output_path.exists():
        print(f"❌ Error: {output_dir}/ directory not found")
        print(f"   Run the pipeline first to generate batch files")
        return False
    
    # Find all batch files
    batch_files = sorted(output_path.glob("batch_*.json"))
    
    if not batch_files:
        print(f"❌ Error: No batch files found in {output_dir}/")
        return False
    
    print(f"📂 Found {len(batch_files)} batch files")
    print(f"🔄 Merging batches...\n")
    
    # Collect all data
    all_nodes = []
    all_relationships = []
    batch_metadata = []
    
    total_processing_time = 0
    min_timestamp = None
    max_timestamp = None
    
    for batch_file in batch_files:
        print(f"  📄 Processing {batch_file.name}...")
        
        with open(batch_file, 'r', encoding='utf-8') as f:
            batch_data = json.load(f)
        
        # Collect nodes and relationships
        all_nodes.extend(batch_data.get('nodes', []))
        all_relationships.extend(batch_data.get('relationships', []))
        
        # Track metadata
        batch_metadata.append({
            "batch_number": batch_data.get('batch_number'),
            "chunk_range": batch_data.get('chunk_range'),
            "nodes_count": batch_data.get('stats', {}).get('nodes_count', 0),
            "relationships_count": batch_data.get('stats', {}).get('relationships_count', 0)
        })
        
        # Track timing
        total_processing_time += batch_data.get('processing_time_seconds', 0)
        
        timestamp = batch_data.get('timestamp')
        if timestamp:
            if min_timestamp is None or timestamp < min_timestamp:
                min_timestamp = timestamp
            if max_timestamp is None or timestamp > max_timestamp:
                max_timestamp = timestamp
    
    # Remove duplicate nodes (by ID)
    print(f"\n🔍 Deduplicating nodes...")
    unique_nodes = {}
    for node in all_nodes:
        node_id = node.get('id')
        if node_id:
            # Keep first occurrence (could also merge properties)
            if node_id not in unique_nodes:
                unique_nodes[node_id] = node
    
    deduplicated_nodes = list(unique_nodes.values())
    duplicates_removed = len(all_nodes) - len(deduplicated_nodes)
    
    if duplicates_removed > 0:
        print(f"  ✅ Removed {duplicates_removed} duplicate nodes")
    
    # Remove duplicate relationships (by source_id + type + target_id)
    print(f"🔍 Deduplicating relationships...")
    unique_rels = {}
    for rel in all_relationships:
        rel_key = (rel.get('source_id'), rel.get('type'), rel.get('target_id'))
        if all(rel_key):
            if rel_key not in unique_rels:
                unique_rels[rel_key] = rel
    
    deduplicated_rels = list(unique_rels.values())
    rel_duplicates_removed = len(all_relationships) - len(deduplicated_rels)
    
    if rel_duplicates_removed > 0:
        print(f"  ✅ Removed {rel_duplicates_removed} duplicate relationships")
    
    # Create merged output
    merged_data = {
        "metadata": {
            "merged_at": datetime.now().isoformat(),
            "source_directory": str(output_path.absolute()),
            "total_batches_merged": len(batch_files),
            "pipeline_start": min_timestamp,
            "pipeline_end": max_timestamp,
            "total_processing_time_seconds": round(total_processing_time, 2)
        },
        "statistics": {
            "total_nodes": len(deduplicated_nodes),
            "total_relationships": len(deduplicated_rels),
            "duplicates_removed": {
                "nodes": duplicates_removed,
                "relationships": rel_duplicates_removed
            }
        },
        "batch_summary": batch_metadata,
        "nodes": deduplicated_nodes,
        "relationships": deduplicated_rels
    }
    
    # Write merged file
    print(f"\n💾 Writing merged file: {output_file}")
    
    indent = 2 if pretty else None
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(merged_data, f, indent=indent, ensure_ascii=False)
    
    file_size_mb = Path(output_file).stat().st_size / (1024 * 1024)
    
    # Print summary
    print(f"\n" + "="*60)
    print(f"✅ MERGE COMPLETED!")
    print(f"="*60)
    print(f"\n📊 Summary:")
    print(f"  • Batches merged: {len(batch_files)}")
    print(f"  • Total nodes: {len(deduplicated_nodes):,}")
    print(f"  • Total relationships: {len(deduplicated_rels):,}")
    print(f"  • Duplicates removed: {duplicates_removed + rel_duplicates_removed:,}")
    print(f"  • Output file: {output_file}")
    print(f"  • File size: {file_size_mb:.2f} MB")
    print(f"\n" + "="*60 + "\n")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Merge batch JSON files into a single file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python merge_batches.py                    # Default output: merged_output.json
  python merge_batches.py --output my.json   # Custom output file
  python merge_batches.py --pretty           # Pretty print with indentation
  python merge_batches.py --dir output2      # Different input directory
        """
    )
    
    parser.add_argument(
        '--output', '-o',
        default='merged_output.json',
        help='Output filename (default: merged_output.json)'
    )
    
    parser.add_argument(
        '--dir', '-d',
        default='output',
        help='Input directory containing batch files (default: output)'
    )
    
    parser.add_argument(
        '--pretty', '-p',
        action='store_true',
        help='Pretty print with indentation (makes file larger)'
    )
    
    args = parser.parse_args()
    
    success = merge_batch_files(
        output_dir=args.dir,
        output_file=args.output,
        pretty=args.pretty
    )
    
    if not success:
        exit(1)


if __name__ == "__main__":
    main()

