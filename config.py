"""
Configuration module for Tamil Medium School Textbooks Auto-Downloader.
STRICT REQUIREMENT: TAMIL MEDIUM ONLY.
"""

import os
from pathlib import Path

# Base URLs for Tamil Nadu School Textbooks
BASE_URL = "https://www.tntextbooks.in"
CLASS_URLS = {
    8: "https://www.tntextbooks.in/p/8th-books.html",
    9: "https://www.tntextbooks.in/p/9th-books.html",
    10: "https://www.tntextbooks.in/p/10th-books.html",
    11: "https://www.tntextbooks.in/p/11th-books.html",
    12: "https://www.tntextbooks.in/p/12th-books.html",
}

# Target Classes and Terms
SUPPORTED_CLASSES = [8, 9, 10, 11, 12]
SUPPORTED_TERMS = ["All Terms", "Term 1", "Term 2", "Term 3", "Full Book"]

# Default download directory (anchored to project folder)
DEFAULT_DOWNLOAD_DIR = str((Path(__file__).parent / "downloads" / "Tamil_Medium").resolve())

# Explicit Whitelist for Tamil Medium Labels (Case-insensitive matching)
TAMIL_MEDIUM_LABELS = [
    "tamil medium",
    "தமிழ் வழி",
    "தமிழ் வழிக்கல்வி",
    "தமிழ்",
    "tamil",
    "tm",
]

# Explicit Blacklist for English & Other Medium Labels
NON_TAMIL_MEDIUM_LABELS = [
    "english medium",
    "english",
    "em",
    "telugu medium",
    "kannada medium",
    "malayalam medium",
    "urdu medium",
]

# Tamil Subject Name Mappings (Unicode Tamil -> English display name)
TAMIL_SUBJECT_TRANSLATIONS = {
    "தமிழ்": "Tamil",
    "ஆங்கிலம்": "English",
    "கணிதம்": "Mathematics",
    "அறிவியல்": "Science",
    "சமூக அறிவியல்": "Social Science",
    "உடற்கல்வி": "Physical Education",
    "சிறப்புத் தமிழ்": "Advanced Tamil",
    "கணக்குப் பதிவியல்": "Accountancy",
    "கணக்குப்பதிவியல்": "Accountancy",
    "உயிர் தாவரவியல்": "Bio-Botany",
    "உயிர் வேதியியல்": "Bio-Chemistry",
    "இயற்பியல்": "Physics",
    "வேதியியல்": "Chemistry",
    "வரலாறு": "History",
    "புவியியல்": "Geography",
    "பொருளியல்": "Economics",
    "வணிகவியல்": "Commerce",
    "கணினி அறிவியல்": "Computer Science",
    "கணினி பயன்பாடுகள்": "Computer Applications",
    "விலங்கியல்": "Zoology",
    "உயிர் விலங்கியல்": "Bio-Zoology",
    "வேளாண் அறிவியல்": "Agricultural Science",
    "வேலைவாய்ப்புத் திறன்கள்": "Employability Skills",
    "தணிக்கையியல்": "Auditing",
    "தணிக்கையியல் செய்முறை": "Auditing Practical",
    "கட்டிடப்பட வரைவாளர்": "Draughtsman Civil",
    "மின் இயந்திரங்களும் சாதனங்களும்": "Electrical Machines and Appliances",
    "அடிப்படைத் தானியங்கி ஊர்திப் பொறியியல்": "Basic Automobile Engineering",
}

# User-Agent for requests
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}
