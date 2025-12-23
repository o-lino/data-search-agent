
import asyncio
import sys
import os

# Add path
sys.path.append('/app')

from tests.performance.data_generator import generate_tables
from rag.optimized_retriever import get_optimized_retriever

async def check():
    print("Generating tables (Mem)...")
    tables = generate_tables(1500)
    
    # Find mem table 1664
    mem_table = next((t for t in tables if t["id"] == 1664), None)
    if not mem_table:
        print("Table 1664 not found in memory generation!")
        return

    print(f"MEM Table 1664: {mem_table['name']}")
    
    print("Fetching from Chroma...")
    retriever = get_optimized_retriever()
    
    # Ensure initialized
    await retriever._ensure_initialized()
    
    # List first 10 IDs
    print("Listing IDs in Chroma...")
    try:
        collection = retriever._client.get_collection("name_embeddings")
        peek = collection.get(limit=10)
        print(f"Found IDs: {peek['ids']}")
        print(f"Total count: {collection.count()}")
    except Exception as e:
        print(f"Error peeking: {e}")

    chroma_table = await retriever.get_table(1664)
    
    if not chroma_table:
        print("Table 1664 not found in Chroma!")
        return
        
    print(f"DB  Table 1664: {chroma_table['name']}")
    
    if mem_table['name'] == chroma_table['name']:
        print("MATCH! ✅")
    else:
        print("MISMATCH! ❌")

if __name__ == "__main__":
    asyncio.run(check())
