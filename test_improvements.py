#!/usr/bin/env python
"""
Quick verification script for RAG improvements.
Tests that all modules import correctly and basic functions work.
"""

import sys
sys.path.insert(0, '/app')

print("=" * 60)
print("RAG IMPROVEMENTS VERIFICATION")
print("=" * 60)

# Test 1: Import coherence analyzer
print("\n[1] Testing CoherenceAnalyzer import...")
try:
    from app.rag.coherence_analyzer import CoherenceAnalyzer
    print("✓ CoherenceAnalyzer imported successfully")
except Exception as e:
    print(f"✗ Failed to import CoherenceAnalyzer: {e}")
    sys.exit(1)

# Test 2: Test coherence scoring
print("\n[2] Testing answer coherence scoring...")
try:
    test_answer = "This is a coherent answer. It has multiple paragraphs.\n\nEach paragraph explores a different aspect. Moreover, they connect naturally."
    result = CoherenceAnalyzer.score_answer_coherence(test_answer)
    print(f"✓ Coherence score: {result['coherence_score']}")
    print(f"  - Is coherent: {result['is_coherent']}")
    print(f"  - Paragraph count: {result['paragraph_count']}")
except Exception as e:
    print(f"✗ Failed to score coherence: {e}")
    sys.exit(1)

# Test 3: Test fragmentation detection
print("\n[3] Testing fragmentation detection...")
try:
    fragmented_answer = "Point 1.\n\nPoint 2.\n\nPoint 3.\n\nPoint 4.\n\nPoint 5."
    result = CoherenceAnalyzer.detect_fragmentation(fragmented_answer)
    print(f"✓ Fragmentation score: {result['fragmentation_score']}")
    print(f"  - Is fragmented: {result['is_fragmented']}")
except Exception as e:
    print(f"✗ Failed to detect fragmentation: {e}")
    sys.exit(1)

# Test 4: Test topic consistency
print("\n[4] Testing topic consistency detection...")
try:
    blocks = [
        "Machine learning is a type of artificial intelligence.",
        "Deep learning uses neural networks with multiple layers.",
        "Natural language processing applies machine learning to text.",
    ]
    result = CoherenceAnalyzer.detect_topic_consistency(blocks)
    print(f"✓ Consistency score: {result['consistency_score']}")
    print(f"  - Dominant topics: {result['dominant_topics']}")
except Exception as e:
    print(f"✗ Failed to detect topic consistency: {e}")
    sys.exit(1)

# Test 5: Import PromptEngineer
print("\n[5] Testing PromptEngineer enhancements...")
try:
    from app.rag.prompt_engineering import PromptEngineer
    print("✓ PromptEngineer imported successfully")
    
    # Test new methods
    test_context = [
        "DOCUMENT: file1.pdf\nPAGE: 1\n\nContent about topic A",
        "DOCUMENT: file2.pdf\nPAGE: 1\n\nContent about topic B",
    ]
    
    signal = PromptEngineer.build_context_synthesis_signal(test_context)
    print(f"✓ Context synthesis signal: {signal[:50]}...")
    
    coherence_signal = PromptEngineer.build_coherence_signal(test_context)
    print(f"✓ Coherence signal: {coherence_signal[:50]}...")
    
except Exception as e:
    print(f"✗ Failed to test PromptEngineer: {e}")
    sys.exit(1)

# Test 6: Test response cleaning
print("\n[6] Testing enhanced response cleaning...")
try:
    test_response = """
    FINAL ANSWER:
    
    This is the first paragraph with some content.
    
    This is the second paragraph with more content. 
    
    However, this is the third paragraph that provides additional context.
    """
    
    cleaned = PromptEngineer.clean_response(test_response)
    print(f"✓ Cleaned response:\n{cleaned}")
    
except Exception as e:
    print(f"✗ Failed to clean response: {e}")
    sys.exit(1)

# Test 7: Test chunk ordering
print("\n[7] Testing chunk ordering for coherence...")
try:
    chunks = [
        {"text": "Content A", "metadata": {"filename": "file1.pdf", "page": "2"}},
        {"text": "Content B", "metadata": {"filename": "file1.pdf", "page": "1"}},
        {"text": "Content C", "metadata": {"filename": "file2.pdf", "page": "1"}},
    ]
    
    ordered = CoherenceAnalyzer.order_chunks_for_coherence(chunks)
    print(f"✓ Chunks reordered: {len(ordered)} chunks")
    for i, chunk in enumerate(ordered):
        meta = chunk.get("metadata", {})
        print(f"  [{i}] {meta.get('filename')} - Page {meta.get('page')}")
    
except Exception as e:
    print(f"✗ Failed to order chunks: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ ALL VERIFICATION TESTS PASSED")
print("=" * 60)
