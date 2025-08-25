import re
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from app.logger import logger


class TitleDateParser:
    """
    Parser for extracting dates from video titles in various formats.
    Supports multiple date formats commonly used in stream VOD titles.
    """
    
    def __init__(self):
        self.date_patterns = [
            # YYYY.MM.DD format: '2025.05.07 fanfan - amogus 3d'
            (r'(\d{4})\.(\d{1,2})\.(\d{1,2})', self._parse_ymd_dot),
            
            # [Mon DD(th|st|nd|rd)?, 'YY] format: '[Jan 24th, '25] Tombs of...'
            (r'\[([A-Za-z]{3})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+\'(\d{2})\]', self._parse_month_day_year_bracket),
            
            # [MM/DD/YY] format: '[10/28/24] Stream VOD'
            (r'\[(\d{1,2})/(\d{1,2})/(\d{2})\]', self._parse_mdy_slash_bracket),
            
            # MM/DD/YYYY format: '10/28/2024 Stream'
            (r'(\d{1,2})/(\d{1,2})/(\d{4})', self._parse_mdy_slash),
            
            # YYYY-MM-DD format: '2025-01-15 Stream'
            (r'(\d{4})-(\d{1,2})-(\d{1,2})', self._parse_ymd_dash),
            
            # Month DD, YYYY format: 'January 15, 2025 Stream'
            (r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', self._parse_month_name_day_year),
            
            # DD Month YYYY format: '15 January 2025 Stream'
            (r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', self._parse_day_month_name_year),
        ]
        
        self.month_names = {
            'jan': 1, 'january': 1,
            'feb': 2, 'february': 2,
            'mar': 3, 'march': 3,
            'apr': 4, 'april': 4,
            'may': 5,
            'jun': 6, 'june': 6,
            'jul': 7, 'july': 7,
            'aug': 8, 'august': 8,
            'sep': 9, 'september': 9,
            'oct': 10, 'october': 10,
            'nov': 11, 'november': 11,
            'dec': 12, 'december': 12,
        }
    
    def extract_date_from_title(self, title: str) -> Optional[datetime]:
        """
        Extract date from video title using various patterns.
        Returns the first valid date found, or None if no date is found.
        """
        for pattern, parser_func in self.date_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                try:
                    date_obj = parser_func(match.groups())
                    if date_obj:
                        logger.info(f"Extracted date {date_obj} from title: '{title[:50]}...'")
                        return date_obj
                except (ValueError, IndexError) as e:
                    logger.debug(f"Failed to parse date with pattern {pattern}: {e}")
                    continue
        
        logger.debug(f"No date found in title: '{title[:50]}...'")
        return None
    
    def _parse_ymd_dot(self, groups: Tuple[str, ...]) -> Optional[datetime]:
        """Parse YYYY.MM.DD format"""
        year, month, day = groups
        return datetime(int(year), int(month), int(day))
    
    def _parse_month_day_year_bracket(self, groups: Tuple[str, ...]) -> Optional[datetime]:
        """Parse [Mon DD, 'YY] format"""
        month_str, day, year = groups
        month = self.month_names.get(month_str.lower())
        if not month:
            return None
        # Convert 2-digit year to 4-digit (assuming 2000s)
        full_year = 2000 + int(year)
        return datetime(full_year, month, int(day))
    
    def _parse_mdy_slash_bracket(self, groups: Tuple[str, ...]) -> Optional[datetime]:
        """Parse [MM/DD/YY] format"""
        month, day, year = groups
        # Convert 2-digit year to 4-digit (assuming 2000s)
        full_year = 2000 + int(year)
        return datetime(full_year, int(month), int(day))
    
    def _parse_mdy_slash(self, groups: Tuple[str, ...]) -> Optional[datetime]:
        """Parse MM/DD/YYYY format"""
        month, day, year = groups
        return datetime(int(year), int(month), int(day))
    
    def _parse_ymd_dash(self, groups: Tuple[str, ...]) -> Optional[datetime]:
        """Parse YYYY-MM-DD format"""
        year, month, day = groups
        return datetime(int(year), int(month), int(day))
    
    def _parse_month_name_day_year(self, groups: Tuple[str, ...]) -> Optional[datetime]:
        """Parse 'Month DD, YYYY' format"""
        month_str, day, year = groups
        month = self.month_names.get(month_str.lower())
        if not month:
            return None
        return datetime(int(year), month, int(day))
    
    def _parse_day_month_name_year(self, groups: Tuple[str, ...]) -> Optional[datetime]:
        """Parse 'DD Month YYYY' format"""
        day, month_str, year = groups
        month = self.month_names.get(month_str.lower())
        if not month:
            return None
        return datetime(int(year), month, int(day))


def extract_date_from_video_title(title: str) -> Optional[datetime]:
    """
    Convenience function to extract date from video title.
    Returns the parsed date or None if no date found.
    """
    parser = TitleDateParser()
    return parser.extract_date_from_title(title)