
import asyncio
import sys
import os

# Add path
sys.path.append('/app')

from rag.optimized_retriever import get_optimized_retriever as get_retriever

async def main():
    print("\n" + "="*50)
    print("[Benchmark] OPERATION: CLEAN ONLY (Per User Request)")
    print("="*50)
    
    retriever = get_retriever(mode="high_accuracy")
    
    # Check current state
    try:
        count_before = await retriever.count()
        print(f"[Benchmark] Found {count_before} tables in ChromaDB.")
    except Exception as e:
        print(f"[Benchmark] Error checking count: {e}")
        count_before = "known"

    # Clear
    print(f"[Benchmark] Clearing database to stop resource usage...")
    try:
        await retriever.clear()
        print("[Benchmark] Database cleared successfully. ✅")
    except Exception as e:
        print(f"[Benchmark] Error during clear: {e}")
    
    # Verify
    try:
        count_after = await retriever.count()
        print(f"[Benchmark] Tables remaining: {count_after}")
    except:
        pass

    print("[Benchmark] Process finished. No indexing or testing performed.")

if __name__ == "__main__":
    asyncio.run(main())
