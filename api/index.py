"""
Vercel Serverless Function entry point for College Admission Enquiry Assistant.
"""

import os
import sys

# Ensure the project root directory is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import application, dispatch

# Vercel looks for 'app' or 'handler'
app = application
handler = application
