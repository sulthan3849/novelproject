import os
import shutil
import tempfile
import unittest
from bs4 import BeautifulSoup, Tag
import ebooklib
from ebooklib import epub
from utils.epub_parser import EpubParser, BLOCK_TAGS, INLINE_TAGS


def create_test_epub(
    file_path: str,
    title: str = "The Chronicles of Aethelgard",
    chapters_content: dict = None,
    include_css: bool = True,
) -> str:
    """Creates a valid, complete EPUB file for testing with NCX and NAV items."""
    book = epub.EpubBook()
    book.set_identifier("urn:uuid:12345-67890-test")
    book.set_title(title)
    book.set_language("en")
    book.add_author("Author McAuthorface")

    # Add standard NCX and NAV items for full EPUB specification compliance
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    if include_css:
        css = epub.EpubItem(
            uid="style_nav",
            file_name="style/main.css",
            media_type="text/css",
            content=b"body { font-family: serif; } em { color: #555; }",
        )
        book.add_item(css)

    spine = ["nav"]

    if chapters_content is None:
        chapters_content = {
            "chapter1.xhtml": (
                "Chapter 1: The Whispering Woods",
                """<?xml version="1.0" encoding="utf-8"?>
                <!DOCTYPE html>
                <html xmlns="http://www.w3.org/1999/xhtml">
                <head><title>Chapter 1</title></head>
                <body>
                    <h1 class="chapter-title">Chapter 1: The Whispering Woods</h1>
                    <p class="narrative">The autumn wind brushed softly against the <em>ancient oak</em> trees.</p>
                    <p class="dialogue" id="d1">"Beware the shadows," warned <span class="character">Elder Lin</span>, clutching his <strong>iron staff</strong>.</p>
                    <blockquote cite="tome">Knowledge is the only shield against the night.</blockquote>
                </body>
                </html>"""
            ),
            "chapter2.xhtml": (
                "Chapter 2: The Silver Blade",
                """<?xml version="1.0" encoding="utf-8"?>
                <!DOCTYPE html>
                <html xmlns="http://www.w3.org/1999/xhtml">
                <head><title>Chapter 2</title></head>
                <body>
                    <h2>Chapter 2: The Silver Blade</h2>
                    <p>He reached into his satchel and withdrew a <a href="lore.xhtml">mysterious scroll</a>.</p>
                    <p>Outside, the rain poured relentlessly.</p>
                </body>
                </html>"""
            ),
        }

    for file_name, (ch_title, html_body) in chapters_content.items():
        ch = epub.EpubHtml(title=ch_title, file_name=file_name, lang="en")
        ch.set_content(html_body.encode("utf-8"))
        book.add_item(ch)
        spine.append(ch)

    book.spine = spine
    epub.write_epub(file_path, book, {})
    return file_path


class TestEpubPipeline(unittest.TestCase):
    """Tier 1 and Tier 2 tests for EPUB parsing, tag preservation, and repacking."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_epub_")
        self.epub_path = os.path.join(self.test_dir, "test_novel.epub")
        create_test_epub(self.epub_path)
        self.parser = EpubParser(self.epub_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _get_chapter_item(self, filename_substr: str):
        """Helper to get a specific chapter item from parser items."""
        for item in self.parser.get_html_items():
            if filename_substr in item.get_name():
                return item
        self.fail(f"Chapter containing '{filename_substr}' not found in EPUB items.")

    # -------------------------------------------------------------
    # Tier 1: Feature Coverage
    # -------------------------------------------------------------

    def test_epub_hash_generation_deterministic(self):
        """Verify compute_hash produces a valid, repeatable 64-char SHA-256 hex string."""
        hash1 = EpubParser.compute_hash(self.epub_path)
        hash2 = EpubParser.compute_hash(self.epub_path)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)
        self.assertEqual(self.parser.book_hash, hash1)

    def test_book_title_and_name_extraction(self):
        """Verify book name and metadata title are correctly extracted."""
        self.assertEqual(self.parser.book_name, "test_novel")
        self.assertEqual(self.parser.title, "The Chronicles of Aethelgard")

    def test_spine_order_retrieval(self):
        """Verify HTML document items are retrieved according to the spine sequence."""
        items = self.parser.get_html_items()
        self.assertGreaterEqual(len(items), 2)
        file_names = [item.get_name() for item in items]
        # Spine contains nav, chapter1.xhtml, chapter2.xhtml
        story_names = [name for name in file_names if not name.startswith("nav")]
        self.assertEqual(len(story_names), 2)
        self.assertIn("chapter1.xhtml", story_names[0])
        self.assertIn("chapter2.xhtml", story_names[1])

    def test_extract_chunks_differentiates_block_from_inline(self):
        """
        Verify extract_chunks isolates block-level elements (p, h1, blockquote)
        and preserves inline tags (em, span, strong) inside their parent.
        """
        ch1 = self._get_chapter_item("chapter1.xhtml")
        soup, nodes = self.parser.extract_chunks(ch1)

        # In Chapter 1: h1, p.narrative, p.dialogue, blockquote -> 4 translatable blocks
        self.assertEqual(len(nodes), 4)

        # Check narrative paragraph has <em> tag preserved inside
        p_narrative = nodes[1]
        self.assertEqual(p_narrative.name, "p")
        self.assertIn("ancient oak", p_narrative.get_text())
        em_child = p_narrative.find("em")
        self.assertIsNotNone(em_child)
        self.assertEqual(em_child.get_text(), "ancient oak")

        # Check dialogue paragraph has span and strong preserved
        p_dialogue = nodes[2]
        self.assertEqual(p_dialogue.get("id"), "d1")
        self.assertIsNotNone(p_dialogue.find("span", class_="character"))
        self.assertIsNotNone(p_dialogue.find("strong"))

    def test_extract_text_nodes_interface_contract(self):
        """Verify extract_text_nodes() returns structured dictionaries matching interface contracts."""
        records = self.parser.extract_text_nodes()
        self.assertIsInstance(records, list)
        self.assertGreater(len(records), 0)

        required_keys = {"item_id", "node_index", "tag", "text", "inner_html", "node"}
        for record in records:
            for key in required_keys:
                self.assertIn(key, record, f"Missing key {key} in extract_text_nodes output")
            self.assertIsInstance(record["node"], Tag)
            self.assertIsInstance(record["inner_html"], str)

    def test_update_node_preserves_outer_attributes_and_replaces_inner_content(self):
        """
        Verify update_node preserves attributes (class, id, style) and
        correctly parses and replaces inner HTML containing inline tags.
        """
        ch1 = self._get_chapter_item("chapter1.xhtml")
        soup, nodes = self.parser.extract_chunks(ch1)
        dialogue_node = nodes[2]

        original_id = dialogue_node.get("id")
        original_class = dialogue_node.get("class")

        translated_html = '"Waspadalah terhadap kegelapan," peringat <span class="character">Tetua Lin</span>, menggenggam <strong>tongkat besinya</strong>.'
        self.parser.update_node(dialogue_node, translated_html)

        # Outer attributes must remain intact
        self.assertEqual(dialogue_node.get("id"), original_id)
        self.assertEqual(dialogue_node.get("class"), original_class)

        # Inner tags must be real BeautifulSoup tags, not escaped text
        span_child = dialogue_node.find("span", class_="character")
        self.assertIsNotNone(span_child)
        self.assertEqual(span_child.get_text(), "Tetua Lin")

        strong_child = dialogue_node.find("strong")
        self.assertIsNotNone(strong_child)
        self.assertEqual(strong_child.get_text(), "tongkat besinya")

    def test_update_node_strips_outer_markdown_code_fences(self):
        """Verify update_node strips ```html code block markers if the model outputs them."""
        ch1 = self._get_chapter_item("chapter1.xhtml")
        soup, nodes = self.parser.extract_chunks(ch1)
        target_node = nodes[1]

        fenced_input = "```html\nAngin musim gugur membelai lembut pepohonan <em>ek kuno</em> itu.\n```"
        self.parser.update_node(target_node, fenced_input)

        self.assertNotIn("```", target_node.get_text())
        em_tag = target_node.find("em")
        self.assertIsNotNone(em_tag)
        self.assertEqual(em_tag.get_text(), "ek kuno")

    def test_update_node_prevents_duplicate_outer_tag_nesting(self):
        """Verify update_node unwraps duplicate outer tags if model returns <p>...</p> for a <p> node."""
        ch1 = self._get_chapter_item("chapter1.xhtml")
        soup, nodes = self.parser.extract_chunks(ch1)
        p_node = nodes[1]
        self.assertEqual(p_node.name, "p")

        duplicate_wrapped = "<p>Terjemahan baru tanpa sarang ganda.</p>"
        self.parser.update_node(p_node, duplicate_wrapped)

        # Should NOT be <p><p>...</p></p>
        nested_p = p_node.find("p")
        self.assertIsNone(nested_p, "update_node created unwanted nested <p> tag inside <p>")
        self.assertEqual(p_node.get_text().strip(), "Terjemahan baru tanpa sarang ganda.")

    def test_epub_repack_produces_valid_epub(self):
        """Verify repack creates a valid EPUB file readable by ebooklib with modified text."""
        ch1 = self._get_chapter_item("chapter1.xhtml")
        soup, nodes = self.parser.extract_chunks(ch1)
        self.parser.update_node(nodes[0], "Bab 1: Hutan yang Berbisik")

        output_path = os.path.join(self.test_dir, "translated.epub")
        returned_path = self.parser.repack(output_path)
        self.assertEqual(returned_path, output_path)
        self.assertTrue(os.path.exists(output_path))
        self.assertGreater(os.path.getsize(output_path), 0)

        # Read repacked EPUB to verify validity
        repacked_book = epub.read_epub(output_path)
        self.assertEqual(repacked_book.get_metadata("DC", "title")[0][0], "The Chronicles of Aethelgard")
        repacked_items = list(repacked_book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        repacked_ch1 = [item for item in repacked_items if "chapter1.xhtml" in item.get_name()][0]
        repacked_content = repacked_ch1.get_content().decode("utf-8")
        self.assertIn("Bab 1: Hutan yang Berbisik", repacked_content)

    def test_save_book_backward_compatible_alias(self):
        """Verify save_book is an alias to repack."""
        out_path = os.path.join(self.test_dir, "saved_book.epub")
        res = self.parser.save_book(out_path)
        self.assertEqual(res, out_path)
        self.assertTrue(os.path.exists(out_path))

    # -------------------------------------------------------------
    # Tier 2: Boundary & Corner Cases
    # -------------------------------------------------------------

    def test_empty_and_whitespace_paragraphs_ignored(self):
        """Verify empty tags <p></p> and whitespace-only tags <p>   </p> are omitted from translatable nodes."""
        empty_html = """<?xml version="1.0" encoding="utf-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <body>
            <p></p>
            <p>   \n   \t  </p>
            <p>Valid translatable sentence.</p>
        </body>
        </html>"""
        item = epub.EpubHtml(title="Empty Test", file_name="empty.xhtml")
        self.parser.book.add_item(item)
        item.set_content(empty_html.encode("utf-8"))

        soup, nodes = self.parser.extract_chunks(item)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].get_text().strip(), "Valid translatable sentence.")

    def test_deep_nested_inline_markup(self):
        """Verify deeply nested inline markup (strong inside em inside span) is preserved."""
        nested_html = """<?xml version="1.0" encoding="utf-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <body>
            <p class="complex">Start <span class="layer1">outer <em>middle <strong>deepest</strong> still-middle</em> back-outer</span> end.</p>
        </body>
        </html>"""
        item = epub.EpubHtml(title="Nested Test", file_name="nested.xhtml")
        self.parser.book.add_item(item)
        item.set_content(nested_html.encode("utf-8"))

        soup, nodes = self.parser.extract_chunks(item)
        self.assertEqual(len(nodes), 1)
        node = nodes[0]

        # Update with translated nested inline tags
        replacement = 'Mulai <span class="layer1">luar <em>tengah <strong>terdalam</strong> masih-tengah</em> kembali-luar</span> akhir.'
        self.parser.update_node(node, replacement)

        self.assertIsNotNone(node.find("strong"))
        self.assertEqual(node.find("strong").get_text(), "terdalam")
        self.assertIsNotNone(node.find("em"))
        self.assertIsNotNone(node.find("span", class_="layer1"))

    def test_japanese_ruby_furigana_markup(self):
        """Verify Japanese ruby and rt tags are preserved."""
        ruby_html = """<?xml version="1.0" encoding="utf-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <body>
            <p>彼の手には<ruby>魔法<rt>まほう</rt></ruby>の剣があった。</p>
        </body>
        </html>"""
        item = epub.EpubHtml(title="Ruby Test", file_name="ruby.xhtml")
        self.parser.book.add_item(item)
        item.set_content(ruby_html.encode("utf-8"))

        soup, nodes = self.parser.extract_chunks(item)
        self.assertEqual(len(nodes), 1)

        # Update preserving ruby tag
        translated = 'Di tangannya tergenggam pedang <ruby>sihir<rt>mahou</rt></ruby> kuno.'
        self.parser.update_node(nodes[0], translated)
        self.assertIsNotNone(nodes[0].find("ruby"))
        self.assertEqual(nodes[0].find("rt").get_text(), "mahou")

    def test_non_standard_and_various_block_elements(self):
        """Verify handling of figcaption, dd, dt, and blockquote."""
        misc_html = """<?xml version="1.0" encoding="utf-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <body>
            <dl>
                <dt>Mana</dt>
                <dd>Energi magis yang mengalir dalam tubuh.</dd>
            </dl>
            <figure>
                <figcaption>Peta Benua Aethelgard.</figcaption>
            </figure>
        </body>
        </html>"""
        item = epub.EpubHtml(title="Misc Test", file_name="misc.xhtml")
        self.parser.book.add_item(item)
        item.set_content(misc_html.encode("utf-8"))

        soup, nodes = self.parser.extract_chunks(item)
        tags_found = {n.name for n in nodes}
        self.assertIn("dt", tags_found)
        self.assertIn("dd", tags_found)
        self.assertIn("figcaption", tags_found)

    def test_corrupted_or_invalid_epub_raises_exception(self):
        """Verify instantiating EpubParser with a corrupt/non-zip file raises appropriate error."""
        corrupt_path = os.path.join(self.test_dir, "corrupt.epub")
        with open(corrupt_path, "wb") as f:
            f.write(b"NOT_A_VALID_ZIP_OR_EPUB_DATA_12345")

        with self.assertRaises(Exception):
            EpubParser(corrupt_path)

    def test_long_paragraph_handling(self):
        """Verify that extremely long paragraphs (15,000+ chars) are processed without error."""
        long_text = "Kalimat panjang ini diulang berkali-kali untuk menguji batas memori. " * 300
        long_html = f"""<?xml version="1.0" encoding="utf-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <body><p class="mammoth">{long_text}</p></body></html>"""
        item = epub.EpubHtml(title="Long Test", file_name="long.xhtml")
        self.parser.book.add_item(item)
        item.set_content(long_html.encode("utf-8"))

        soup, nodes = self.parser.extract_chunks(item)
        self.assertEqual(len(nodes), 1)
        self.assertGreater(len(nodes[0].get_text()), 15000)


if __name__ == "__main__":
    unittest.main()
