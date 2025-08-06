#!/usr/bin/env python3
"""
Test script to compare Python vs Rust search performance
"""
import time
from app.search import search_words_present_in_sentence, search_words_present_in_sentence_strict

# Test data
sentence = ["the", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]
search_words = ["fox", "jumps"]
strict_search_words = ["quick", "brown", "fox"]

def test_python_functions():
    """Test Python implementations"""
    print("Testing Python functions:")
    
    # Regular search
    start = time.perf_counter()
    for _ in range(10000):
        result = search_words_present_in_sentence(sentence, search_words)
    python_regular_time = time.perf_counter() - start
    print(f"Python regular search result: {result}")
    print(f"Python regular search (10k iterations): {python_regular_time*1000:.2f}ms")
    
    # Strict search
    start = time.perf_counter()
    for _ in range(10000):
        result = search_words_present_in_sentence_strict(sentence, strict_search_words)
    python_strict_time = time.perf_counter() - start
    print(f"Python strict search result: {result}")
    print(f"Python strict search (10k iterations): {python_strict_time*1000:.2f}ms")
    
    return python_regular_time, python_strict_time

def test_rust_functions():
    """Test Rust implementations"""
    try:
        import yappr_search
        print("\nTesting Rust functions:")
        
        # Regular search
        start = time.perf_counter()
        for _ in range(10000):
            result = yappr_search.search_words_present_in_sentence(sentence, search_words)
        rust_regular_time = time.perf_counter() - start
        print(f"Rust regular search result: {result}")
        print(f"Rust regular search (10k iterations): {rust_regular_time*1000:.2f}ms")
        
        # Strict search
        start = time.perf_counter()
        for _ in range(10000):
            result = yappr_search.search_words_present_in_sentence_strict(sentence, strict_search_words)
        rust_strict_time = time.perf_counter() - start
        print(f"Rust strict search result: {result}")
        print(f"Rust strict search (10k iterations): {rust_strict_time*1000:.2f}ms")
        
        return rust_regular_time, rust_strict_time
    except ImportError:
        print("\nRust module not available - build with: uv run maturin develop")
        return None, None

if __name__ == "__main__":
    python_times = test_python_functions()
    rust_times = test_rust_functions()
    
    if rust_times[0] is not None:
        print(f"\nPerformance comparison:")
        print(f"Regular search speedup: {python_times[0]/rust_times[0]:.2f}x")
        print(f"Strict search speedup: {python_times[1]/rust_times[1]:.2f}x")