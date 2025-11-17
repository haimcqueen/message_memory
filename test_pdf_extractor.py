"""Test script to run PDF through the extractor."""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from workers.media import parse_pdf_with_openai

def test_pdf_extraction():
    """Test PDF extraction with CV."""
    pdf_path = Path(__file__).parent / "test_files" / "CV_Hai_Bui (1).pdf"

    print(f"Reading PDF from: {pdf_path}")

    with open(pdf_path, "rb") as f:
        pdf_content = f.read()

    print(f"PDF size: {len(pdf_content)} bytes")
    print("\n" + "="*80)
    print("Extracting content with OpenAI...")
    print("="*80 + "\n")

    try:
        extracted_content = parse_pdf_with_openai(pdf_content, filename="CV_Hai_Bui.pdf")

        print("EXTRACTED CONTENT:")
        print("="*80)
        print(extracted_content)
        print("="*80)
        print(f"\nExtracted {len(extracted_content)} characters")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pdf_extraction()
