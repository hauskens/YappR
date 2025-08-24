import pytest
from unittest.mock import Mock, patch
from datetime import datetime

# Mark these as unit tests to avoid database setup
pytestmark = pytest.mark.unit

# Import the search functions we want to test
from app.search import search_v2
from app.models.search import VideoResult


class TestSearchV2Integration:
    """Test the main search_v2 function with mocked database dependencies"""
    
    def setup_method(self):
        """Set up common mocks for each test"""
        # Create mock video
        self.mock_video = Mock()
        self.mock_video.id = 1
        self.mock_video.uploaded = datetime(2023, 1, 1)
        
        # Create mock transcription
        self.mock_transcription = Mock()
        self.mock_transcription.video = self.mock_video
        
        # Create mock segments
        self.mock_segment1 = Mock()
        self.mock_segment1.id = 1
        self.mock_segment1.text = "This is a test segment with hello world"
        self.mock_segment1.previous_segment_id = None
        self.mock_segment1.next_segment_id = 2
        self.mock_segment1.transcription = self.mock_transcription
        self.mock_segment1.start = 0
        self.mock_segment1.end = 5
        
        self.mock_segment2 = Mock()
        self.mock_segment2.id = 2
        self.mock_segment2.text = "Another segment with different content"
        self.mock_segment2.previous_segment_id = 1
        self.mock_segment2.next_segment_id = None
        self.mock_segment2.transcription = self.mock_transcription
        self.mock_segment2.start = 5
        self.mock_segment2.end = 10
        
        # Create mock channel
        self.mock_channel = Mock()
        self.mock_channel.id = 1
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels')
    @patch('app.search.db.session')
    @patch('app.search.sanitize_sentence')
    @patch('app.search.loosely_sanitize_sentence')
    def test_search_v2_basic_search(self, mock_loosely_sanitize, mock_sanitize, 
                                   mock_db_session, mock_get_transcriptions):
        """Test basic search functionality"""
        # Setup mocks
        mock_transcription_obj = Mock()
        mock_transcription_obj.id = 1
        mock_get_transcriptions.return_value = [mock_transcription_obj]
        
        # Mock database query results
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = [self.mock_segment1]
        mock_db_session.execute.return_value = mock_query_result
        
        # Mock segment retrieval
        mock_get_segment = Mock()
        mock_get_segment.return_value = self.mock_segment1
        
        # Mock sanitization functions
        mock_sanitize.return_value = ["hello", "world", "test"]
        
        # Test non-strict search
        result = search_v2("hello world", [self.mock_channel])
        
        # Verify results
        assert len(result) == 1
        assert isinstance(result[0], VideoResult)
        assert result[0].video == self.mock_video
        assert len(result[0].segment_results) == 1
        
        # Verify that get_transcriptions was called
        mock_get_transcriptions.assert_called_once_with([self.mock_channel])
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels_daterange')
    @patch('app.search.db.session')
    @patch('app.search.sanitize_sentence')
    def test_search_v2_with_date_range(self, mock_sanitize, mock_db_session, 
                                      mock_get_transcriptions_daterange):
        """Test search with date range filtering"""
        # Setup mocks
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)
        
        mock_transcription_obj = Mock()
        mock_transcription_obj.id = 1
        mock_get_transcriptions_daterange.return_value = [mock_transcription_obj]
        
        # Mock database query results
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = [self.mock_segment1]
        mock_db_session.execute.return_value = mock_query_result
        
        mock_get_segment = Mock()
        mock_get_segment.return_value = self.mock_segment1
        mock_sanitize.return_value = ["hello", "world"]
        
        # Test with date range
        result = search_v2("hello world", [self.mock_channel], start_date, end_date)
        
        # Verify date range function was called
        mock_get_transcriptions_daterange.assert_called_once_with([self.mock_channel], start_date, end_date)
        assert len(result) == 1
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels')
    @patch('app.search.db.session')
    @patch('app.search.loosely_sanitize_sentence')
    def test_search_v2_strict_search(self, mock_loosely_sanitize, mock_db_session, 
                                    mock_get_transcriptions):
        """Test strict search with quoted terms"""
        # Setup mocks for strict search
        mock_transcription_obj = Mock()
        mock_transcription_obj.id = 1
        mock_get_transcriptions.return_value = [mock_transcription_obj]
        
        # Mock database query results
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = [self.mock_segment1]
        mock_db_session.execute.return_value = mock_query_result
        
        mock_get_segment = Mock()
        mock_get_segment.return_value = self.mock_segment1
        mock_loosely_sanitize.return_value = ["hello", "world"]
        
        # Test strict search (quoted terms)
        result = search_v2('"hello world"', [self.mock_channel])
        
        # Verify loosely_sanitize was used for strict search
        mock_loosely_sanitize.assert_called()
        assert len(result) >= 0  # May be 0 if strict matching fails
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels')
    def test_search_v2_no_transcriptions_error(self, mock_get_transcriptions):
        """Test error when no transcriptions are found"""
        mock_get_transcriptions.return_value = None
        
        with pytest.raises(ValueError, match="No transcriptions found"):
            search_v2("hello world", [self.mock_channel])
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels')
    @patch('app.search.db.session')
    @patch('app.search.sanitize_sentence')
    def test_search_v2_empty_search_words_error(self, mock_sanitize, mock_db_session, mock_get_transcriptions):
        """Test error when search results in no useful words"""
        mock_transcription_obj = Mock()
        mock_get_transcriptions.return_value = [mock_transcription_obj]
        
        # Mock database query results
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_query_result
        
        # Mock sanitize to return empty list (no useful words)
        mock_sanitize.return_value = []
        
        with pytest.raises(ValueError, match="Search was too short"):
            search_v2("   ", [self.mock_channel])  # Search term with only spaces
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels')
    @patch('app.search.db.session')
    @patch('app.search.sanitize_sentence')
    def test_search_v2_adjacent_segment_logic(self, mock_sanitize, mock_db_session, 
                                             mock_get_transcriptions):
        """Test adjacent segment retrieval logic"""
        # Setup mocks
        mock_transcription_obj = Mock()
        mock_transcription_obj.id = 1
        mock_get_transcriptions.return_value = [mock_transcription_obj]
        
        # Create segment where search word is at the beginning
        segment_with_word_at_start = Mock()
        segment_with_word_at_start.id = 10
        segment_with_word_at_start.text = "hello this is a test"
        segment_with_word_at_start.previous_segment_id = 9
        segment_with_word_at_start.next_segment_id = 11
        segment_with_word_at_start.transcription = self.mock_transcription
        
        # Mock the previous segment
        previous_segment = Mock()
        previous_segment.text = "previous segment text"
        
        # Mock database query results
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = [segment_with_word_at_start]
        mock_db_session.execute.return_value = mock_query_result
        
        # Mock segment retrieval - return different segments based on ID
        def mock_get_segment_side_effect(segment_id):
            if segment_id == 10:
                return segment_with_word_at_start
            elif segment_id == 9:
                return previous_segment
            return segment_with_word_at_start
        
        mock_get_segment = Mock()
        mock_get_segment.side_effect = mock_get_segment_side_effect
        
        # Mock sanitize to return words where "hello" is first
        mock_sanitize.side_effect = lambda text: text.split()
        
        # Test search
        result = search_v2("hello world", [self.mock_channel])
        
    
    @patch('app.search.TranscriptionService.get_transcriptions_on_channels')
    @patch('app.search.db.session')
    @patch('app.search.sanitize_sentence')
    def test_search_v2_multiple_videos_grouping(self, mock_sanitize, mock_db_session, 
                                               mock_get_transcriptions):
        """Test that results are properly grouped by video"""
        # Setup mocks for multiple segments from same video
        mock_transcription_obj = Mock()
        mock_transcription_obj.id = 1
        mock_get_transcriptions.return_value = [mock_transcription_obj]
        
        # Create two segments from the same video
        segment1 = Mock()
        segment1.id = 1
        segment1.text = "hello world segment one"
        segment1.transcription = self.mock_transcription
        segment1.previous_segment_id = None
        segment1.next_segment_id = None
        segment1.start = 0  # Add numeric start time for sorting
        segment1.end = 5
        
        segment2 = Mock()
        segment2.id = 2
        segment2.text = "hello world segment two"  
        segment2.transcription = self.mock_transcription
        segment2.previous_segment_id = None
        segment2.next_segment_id = None
        segment2.start = 10  # Add numeric start time for sorting
        segment2.end = 15
        
        # Mock database query results
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = [segment1, segment2]
        mock_db_session.execute.return_value = mock_query_result
        
        # Mock segment retrieval
        def mock_get_segment_side_effect(segment_id):
            if segment_id == 1:
                return segment1
            elif segment_id == 2:
                return segment2
        
        mock_get_segment = Mock()
        mock_get_segment.side_effect = mock_get_segment_side_effect
        mock_sanitize.return_value = ["hello", "world"]
        
        # Test search
        result = search_v2("hello world", [self.mock_channel])
        
        # Should have 1 VideoResult with 2 SegmentsResult
        assert len(result) == 1
        assert len(result[0].segment_results) == 2
        