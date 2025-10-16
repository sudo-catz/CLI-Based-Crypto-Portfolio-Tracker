#!/usr/bin/env python3
"""
Test script to verify the file saving fixes
"""

import os
import sys
import tempfile
import json
from datetime import datetime
from pathlib import Path

# Add current directory to Python path for imports
sys.path.insert(0, os.getcwd())


def test_portfolio_analyzer_save_path():
    """Test that PortfolioAnalyzer saves files to the correct directory."""
    print("🧪 Testing PortfolioAnalyzer file saving...")

    try:
        from core.portfolio_analyzer import PortfolioAnalyzer

        # Create analyzer instance
        analyzer = PortfolioAnalyzer(None, None)

        # Test data
        test_data = {
            "timestamp": datetime.now().isoformat(),
            "total_portfolio_value": 1000.0,
            "test": True,
        }

        # Save the analysis
        analyzer.save_portfolio_analysis(test_data)

        # Check if file was created in correct location
        analysis_files = list(Path("data/analysis").glob("portfolio_analysis_*.json"))
        if analysis_files:
            latest_file = max(analysis_files, key=os.path.getctime)
            print(f"✅ Portfolio analysis saved correctly to: {latest_file}")

            # Verify content
            with open(latest_file, "r") as f:
                saved_data = json.load(f)
                if saved_data.get("test") == True:
                    print("✅ File content verified")
                    return True
                else:
                    print("❌ File content mismatch")
                    return False
        else:
            print("❌ No analysis file found in data/analysis/")
            return False

    except Exception as e:
        print(f"❌ Error testing PortfolioAnalyzer: {e}")
        return False


def test_directory_structure():
    """Test that directories are created properly."""
    print("\n🧪 Testing directory structure...")

    required_dirs = ["data/analysis", "data/screenshots"]

    all_exist = True
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"✅ Directory exists: {dir_path}")
        else:
            print(f"❌ Directory missing: {dir_path}")
            all_exist = False

    return all_exist


def test_imports():
    """Test that all main modules can be imported."""
    print("\n🧪 Testing module imports...")

    modules_to_test = ["core.portfolio_analyzer", "wallets.fetchers", "ui.menus"]

    all_imported = True
    for module_name in modules_to_test:
        try:
            __import__(module_name)
            print(f"✅ Successfully imported: {module_name}")
        except ImportError as e:
            print(f"❌ Failed to import {module_name}: {e}")
            all_imported = False

    return all_imported


def main():
    """Run all tests."""
    print("🔧 TESTING FILE SAVING FIXES")
    print("=" * 50)

    tests = [
        ("Module Imports", test_imports),
        ("Directory Structure", test_directory_structure),
        ("Portfolio Analyzer Save Path", test_portfolio_analyzer_save_path),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")

    print("\n" + "=" * 50)
    print(f"🎯 TEST RESULTS: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 ALL TESTS PASSED! File saving fixes are working correctly.")
        return True
    else:
        print(f"⚠️  {total - passed} tests failed. Please review the issues above.")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
