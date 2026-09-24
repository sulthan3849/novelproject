import sys, os
sys.path.insert(0, os.path.abspath("."))
import unittest
from bs4 import BeautifulSoup
from utils.epub_parser import EpubParser
import ebooklib
from ebooklib import epub

class TestDivNesting(unittest.TestCase):
    def test_nested_divs_without_block_tags(self):
        html = """
        <div class="outer">
            <div class="middle">
                <div class="inner">Hello from inner div</div>
            </div>
        </div>
        """
        book = epub.EpubBook()
        item = epub.EpubHtml(title="Div Test", file_name="div_test.xhtml")
        item.set_content(html.encode("utf-8"))
        book.add_item(item)
        
        parser = EpubParser.__new__(EpubParser)
        parser._item_soups = {}
        soup, nodes = parser.extract_chunks(item)
        
        print(f"Extracted nodes count: {len(nodes)}")
        for i, n in enumerate(nodes):
            print(f"Node {i}: tag={n.name}, class={n.get('class')}, text={n.get_text().strip()!r}")

if __name__ == "__main__":
    unittest.main()
