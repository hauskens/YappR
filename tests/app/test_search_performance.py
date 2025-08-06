import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from collections.abc import Sequence

# Mark these as unit tests to avoid database setup
pytestmark = pytest.mark.unit

from app.search import (
    search_words_present_in_sentence,
    search_words_present_in_sentence_strict,
    search_v2,
)


class TestSearchPerformance:
    """Performance benchmarks for search functions"""
    
    def setup_method(self):
        """Set up mock data for performance testing"""
        # Create mock video
        self.mock_video = Mock()
        self.mock_video.id = 1
        self.mock_video.uploaded = datetime(2023, 1, 1)
        
        # Create mock transcription
        self.mock_transcription = Mock()
        self.mock_transcription.video = self.mock_video
        
        # Create mock channel
        self.mock_channel = Mock()
        self.mock_channel.id = 1
    
    def create_mock_segments(self, count: int, text_template: str = "This is segment {} with some test content"):
        """Create a list of mock segments for testing"""
        segments = []
        for i in range(count):
            segment = Mock()
            segment.id = i
            segment.text = text_template.format(i)
            segment.transcription = self.mock_transcription
            segment.previous_segment_id = i - 1 if i > 0 else None
            segment.next_segment_id = i + 1 if i < count - 1 else None
            segment.start = i * 10
            segment.end = (i + 1) * 10
            segments.append(segment)
        return segments
    
    def benchmark_search_helper_functions(self):
        """Benchmark the basic search helper functions"""
        # Test data
        sentence = ["the", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]
        search_words = ["quick", "brown", "fox"]
        
        # Benchmark regular search
        start_time = time.perf_counter()
        for _ in range(10000):
            search_words_present_in_sentence(sentence, search_words)
        regular_time = time.perf_counter() - start_time
        
        # Benchmark strict search
        start_time = time.perf_counter()
        for _ in range(10000):
            search_words_present_in_sentence_strict(sentence, search_words)
        strict_time = time.perf_counter() - start_time
        
        print(f"\nHelper Function Performance (10k iterations):")
        print(f"Regular search: {regular_time*1000:.2f}ms")
        print(f"Strict search: {strict_time*1000:.2f}ms")
        
        # Assertions to ensure functions still work
        assert search_words_present_in_sentence(sentence, search_words) == True
        assert search_words_present_in_sentence_strict(sentence, search_words) == True
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels')
    @patch('app.search.SegmentService.get_by_id')
    @patch('app.search.db.session')
    @patch('app.search.sanitize_sentence')
    def test_search_v2_performance_small_dataset(self, mock_sanitize, mock_db_session, 
                                                mock_get_segment, mock_get_transcriptions):
        """Test search performance with small dataset (100 segments)"""
        self._run_search_performance_test(
            mock_sanitize, mock_db_session, mock_get_segment, mock_get_transcriptions,
            segment_count=100, test_name="Small Dataset (100 segments)"
        )
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels')
    @patch('app.search.SegmentService.get_by_id')
    @patch('app.search.db.session')
    @patch('app.search.sanitize_sentence')
    def test_search_v2_performance_medium_dataset(self, mock_sanitize, mock_db_session, 
                                                 mock_get_segment, mock_get_transcriptions):
        """Test search performance with medium dataset (1000 segments)"""
        self._run_search_performance_test(
            mock_sanitize, mock_db_session, mock_get_segment, mock_get_transcriptions,
            segment_count=1000, test_name="Medium Dataset (1000 segments)"
        )
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels')
    @patch('app.search.SegmentService.get_by_id')
    @patch('app.search.db.session')
    @patch('app.search.sanitize_sentence')
    def test_search_v2_performance_large_dataset(self, mock_sanitize, mock_db_session, 
                                                mock_get_segment, mock_get_transcriptions):
        """Test search performance with large dataset (5000 segments)"""
        self._run_search_performance_test(
            mock_sanitize, mock_db_session, mock_get_segment, mock_get_transcriptions,
            segment_count=5000, test_name="Large Dataset (5000 segments)"
        )
    
    def _run_search_performance_test(self, mock_sanitize, mock_db_session, 
                                   mock_get_segment, mock_get_transcriptions,
                                   segment_count: int, test_name: str):
        """Run a performance test with specified number of segments"""
        # Setup mocks
        mock_transcription_obj = Mock()
        mock_transcription_obj.id = 1
        mock_get_transcriptions.return_value = [mock_transcription_obj]
        
        # Create mock segments
        segments = self.create_mock_segments(
            segment_count, 
            "This is test segment {} with hello world and other content"
        )
        
        # Mock database query results
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = segments
        mock_db_session.execute.return_value = mock_query_result
        
        # Mock segment retrieval (return the segment itself)
        def mock_get_segment_side_effect(segment_id):
            return next((s for s in segments if s.id == segment_id), segments[0])
        
        mock_get_segment.side_effect = mock_get_segment_side_effect
        
        # Mock sanitization - return words that will match some segments
        mock_sanitize.return_value = ["hello", "world", "test"]
        
        # Run performance test
        start_time = time.perf_counter()
        result = search_v2("hello world", [self.mock_channel])
        end_time = time.perf_counter()
        
        execution_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        print(f"\n{test_name}:")
        print(f"Execution time: {execution_time:.2f}ms")
        print(f"Segments processed: {segment_count}")
        print(f"Results found: {len(result)}")
        print(f"Time per segment: {execution_time/segment_count:.4f}ms")
        
        # Performance assertions
        assert execution_time < 5000, f"Search took too long: {execution_time:.2f}ms"
        assert len(result) > 0, "Should find at least one result"
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels')
    @patch('app.search.SegmentService.get_by_id')
    @patch('app.search.db.session')
    @patch('app.search.sanitize_sentence')
    def test_search_v2_performance_with_adjacent_segments(self, mock_sanitize, mock_db_session, 
                                                         mock_get_segment, mock_get_transcriptions):
        """Test performance when adjacent segment logic is triggered frequently"""
        # Setup mocks
        mock_transcription_obj = Mock()
        mock_transcription_obj.id = 1
        mock_get_transcriptions.return_value = [mock_transcription_obj]
        
        # Create segments where search word appears at the beginning (triggers adjacent logic)
        segments = []
        for i in range(500):
            segment = Mock()
            segment.id = i
            # Make every segment start with search word to trigger adjacent logic
            segment.text = f"hello this is segment {i} with more content"
            segment.transcription = self.mock_transcription
            segment.previous_segment_id = i - 1 if i > 0 else None
            segment.next_segment_id = i + 1 if i < 499 else None
            segment.start = i * 10
            segment.end = (i + 1) * 10
            segments.append(segment)
        
        # Mock database query results
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = segments
        mock_db_session.execute.return_value = mock_query_result
        
        # Mock segment retrieval
        def mock_get_segment_side_effect(segment_id):
            return next((s for s in segments if s.id == segment_id), segments[0])
        
        mock_get_segment.side_effect = mock_get_segment_side_effect
        
        # Mock sanitization to return split words
        mock_sanitize.side_effect = lambda text: text.split()
        
        # Run performance test
        start_time = time.perf_counter()
        result = search_v2("hello world", [self.mock_channel])
        end_time = time.perf_counter()
        
        execution_time = (end_time - start_time) * 1000
        
        print(f"\nAdjacent Segment Performance Test:")
        print(f"Execution time: {execution_time:.2f}ms")
        print(f"Segments with adjacent logic: 500")
        print(f"get_segment_by_id calls: {mock_get_segment.call_count}")
        print(f"Time per segment: {execution_time/500:.4f}ms")
        
        # Performance assertion - should still be reasonably fast
        assert execution_time < 10000, f"Search with adjacent segments took too long: {execution_time:.2f}ms"
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels')
    @patch('app.search.SegmentService.get_by_id')
    @patch('app.search.db.session')
    @patch('app.search.loosely_sanitize_sentence')
    def test_search_v2_strict_search_performance(self, mock_loosely_sanitize, mock_db_session, 
                                                mock_get_segment, mock_get_transcriptions):
        """Test performance of strict search (quoted terms)"""
        # Setup mocks
        mock_transcription_obj = Mock()
        mock_transcription_obj.id = 1
        mock_get_transcriptions.return_value = [mock_transcription_obj]
        
        # Create segments with various phrase patterns
        segments = []
        for i in range(1000):
            segment = Mock()
            segment.id = i
            if i % 3 == 0:
                segment.text = f"This contains hello world phrase in segment {i}"
            elif i % 3 == 1:
                segment.text = f"This has hello and world separated in segment {i}"
            else:
                segment.text = f"Random content in segment {i} without target"
            segment.transcription = self.mock_transcription
            segment.previous_segment_id = None
            segment.next_segment_id = None
            segment.start = i * 10
            segment.end = (i + 1) * 10
            segments.append(segment)
        
        # Mock database query results
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = segments
        mock_db_session.execute.return_value = mock_query_result
        
        # Mock segment retrieval
        def mock_get_segment_side_effect(segment_id):
            return next((s for s in segments if s.id == segment_id), segments[0])
        
        mock_get_segment.side_effect = mock_get_segment_side_effect
        
        # Mock sanitization for strict search
        mock_loosely_sanitize.side_effect = lambda text: text.split()
        
        # Run strict search performance test
        start_time = time.perf_counter()
        result = search_v2('"hello world"', [self.mock_channel])  # Quoted for strict search
        end_time = time.perf_counter()
        
        execution_time = (end_time - start_time) * 1000
        
        print(f"\nStrict Search Performance Test:")
        print(f"Execution time: {execution_time:.2f}ms")
        print(f"Segments processed: 1000")
        print(f"Results found: {len(result)}")
        print(f"Time per segment: {execution_time/1000:.4f}ms")
        
        # Performance assertion
        assert execution_time < 5000, f"Strict search took too long: {execution_time:.2f}ms"
    
    def test_run_all_performance_benchmarks(self):
        """Run all performance benchmarks and display summary"""
        print("\n" + "="*60)
        print("SEARCH PERFORMANCE BENCHMARK SUITE")
        print("="*60)
        
        # Run helper function benchmarks
        self.benchmark_search_helper_functions()
        
        print("\n" + "="*60)
        print("Performance benchmarks completed!")
        print("="*60)


class TestSearchScalability:
    """Test how search performance scales with different parameters"""
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels')
    @patch('app.search.SegmentService.get_by_id')
    @patch('app.search.db.session')
    @patch('app.search.sanitize_sentence')
    def test_search_scalability_by_result_size(self, mock_sanitize, mock_db_session, 
                                              mock_get_segment, mock_get_transcriptions):
        """Test how performance changes with different result set sizes"""
        # Setup basic mocks
        mock_transcription_obj = Mock()
        mock_transcription_obj.id = 1
        mock_get_transcriptions.return_value = [mock_transcription_obj]
        
        mock_video = Mock()
        mock_video.id = 1
        mock_video.uploaded = datetime(2023, 1, 1)
        
        mock_transcription = Mock()
        mock_transcription.video = mock_video
        
        mock_channel = Mock()
        mock_channel.id = 1
        
        # Test with different result sizes
        result_sizes = [10, 50, 100, 500, 1000]
        performance_data = []
        
        for size in result_sizes:
            # Create segments where all match the search
            segments = []
            for i in range(size):
                segment = Mock()
                segment.id = i
                segment.text = f"hello world segment {i}"
                segment.transcription = mock_transcription
                segment.previous_segment_id = None
                segment.next_segment_id = None
                segment.start = i * 10
                segment.end = (i + 1) * 10
                segments.append(segment)
            
            # Mock database query results
            mock_query_result = Mock()
            mock_query_result.scalars.return_value.all.return_value = segments
            mock_db_session.execute.return_value = mock_query_result
            
            # Mock segment retrieval
            def mock_get_segment_side_effect(segment_id):
                return next((s for s in segments if s.id == segment_id), segments[0])
            
            mock_get_segment.side_effect = mock_get_segment_side_effect
            mock_sanitize.return_value = ["hello", "world"]
            
            # Measure performance
            start_time = time.perf_counter()
            result = search_v2("hello world", [mock_channel])
            end_time = time.perf_counter()
            
            execution_time = (end_time - start_time) * 1000
            performance_data.append((size, execution_time))
        
        print(f"\nScalability Test - Performance by Result Size:")
        print("Results | Time (ms) | Time/Result (ms)")
        print("-" * 40)
        for size, time_ms in performance_data:
            time_per_result = time_ms / size
            print(f"{size:7d} | {time_ms:8.2f} | {time_per_result:13.4f}")
        
        # Check that performance doesn't degrade too badly
        # Linear scaling should be acceptable
        first_time_per_result = performance_data[0][1] / performance_data[0][0]
        last_time_per_result = performance_data[-1][1] / performance_data[-1][0]
        
        # Allow up to 5x degradation (should be much better in practice)
        assert last_time_per_result < first_time_per_result * 5, \
            f"Performance degraded too much: {first_time_per_result:.4f}ms -> {last_time_per_result:.4f}ms per result"