#!/usr/bin/env python3
"""
Quick verification script to check that reports are saved to Qdrant database.

This script helps you verify:
1. Database connection is working
2. Reports are properly saved
3. Reports can be retrieved
"""

import os
from src.db.database import VectorDBContext

def verify_database():
    """Verify Qdrant database is working."""
    print("\n" + "=" * 80)
    print("  Qdrant Database Verification")
    print("=" * 80)
    
    # Check environment
    qdrant_url = os.environ.get("QDRANT_URL")
    qdrant_key = os.environ.get("QDRANT_API_KEY")
    
    print("\n1. Environment Configuration:")
    print(f"   QDRANT_URL: {qdrant_url or '(using in-memory)'}")
    print(f"   QDRANT_API_KEY: {'[SET]' if qdrant_key else '[NOT SET - will use in-memory]'}")
    
    # Initialize database
    print("\n2. Initializing Qdrant Database:")
    db = VectorDBContext()
    print("   ✓ Connected to Qdrant")
    
    try:
        db.init_db()
        print("   ✓ Collection created/verified")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # Check existing reports
    print("\n3. Checking Stored Reports:")
    reports = db.get_reports()
    print(f"   Total reports in database: {len(reports)}")
    
    if reports:
        print("\n   Stored Reports:")
        for i, report in enumerate(reports, 1):
            query = report.get('query', 'N/A')[:50]
            report_len = len(report.get('report', ''))
            print(f"   {i}. Query: {query}...")
            print(f"      Report size: {report_len} characters")
            print(f"      ID: {report.get('id')}\n")
    else:
        print("   (No reports stored yet)")
    
    # Test save functionality
    print("4. Testing Save Functionality:")
    test_query = "Test query for verification"
    test_report = "This is a test report content that should be saved to Qdrant."
    
    try:
        db.save_report(test_query, test_report)
        print("   ✓ Test report saved successfully")
    except Exception as e:
        print(f"   ✗ Error saving test report: {e}")
        return False
    
    # Verify save
    updated_reports = db.get_reports()
    if len(updated_reports) > len(reports):
        print("   ✓ Verified: Report appears in database")
        return True
    else:
        print("   ✗ Error: Report not found in database")
        return False

if __name__ == "__main__":
    success = verify_database()
    
    if success:
        print("\n" + "=" * 80)
        print("  ✓ All Verifications Passed!")
        print("=" * 80)
        print("\nReports are being properly saved to Qdrant database.")
        print("The issue with missing local files has been resolved.")
    else:
        print("\n" + "=" * 80)
        print("  ✗ Some verifications failed")
        print("=" * 80)
