import hashlib
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, NavigableString, Tag

# Block-level elements that form independent translation units
BLOCK_TAGS = {
    "p", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "dd", "dt", "pre", "figcaption",
    "td", "th", "aside", "caption", "section"
}

# Inline formatting tags that must be preserved within a block element
INLINE_TAGS = {
    "em", "strong", "span", "a", "i", "b", "ruby", "rt", "rp",
    "small", "sub", "sup", "code", "mark", "u", "s", "cite",
    "abbr", "q", "font"
}


class EpubParser:
    """
    Parser and repacker for EPUB novels.
    Preserves document structure, CSS classes, inline tags (em, span, b, ruby),
    and tracks document items across the spine.
    """

    def __init__(self, file_path: str, book_hash: Optional[str] = None):
        self.file_path = file_path
        self.book = epub.read_epub(self.file_path)
        
        # Calculate or assign stable content SHA-256 hash
        self.book_hash = book_hash or self.compute_hash(self.file_path)
        
        # Determine book name and internal title metadata
        self.book_name = os.path.splitext(os.path.basename(file_path))[0]
        titles = self.book.get_metadata("DC", "title")
        self.title = titles[0][0] if titles else self.book_name

        # Map to track modified soup objects per item ID for auto-sync before repacking
        self._item_soups: Dict[str, Tuple[Any, BeautifulSoup]] = {}

    @staticmethod
    def compute_hash(file_path: str) -> str:
        """Compute SHA-256 hash of the EPUB file bytes for deterministic session keying."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_html_items(self) -> List[Any]:
        """
        Retrieves all HTML document items from the EPUB in reading/spine order.
        Falls back to get_items_of_type(ITEM_DOCUMENT) if spine is unpopulated.
        """
        all_docs = {item.get_id(): item for item in self.book.get_items_of_type(ebooklib.ITEM_DOCUMENT)}
        ordered_items = []
        
        # Attempt spine ordering
        spine_ids = [entry[0] for entry in getattr(self.book, "spine", []) if entry]
        seen_ids = set()
        
        for item_id in spine_ids:
            if item_id in all_docs and item_id not in seen_ids:
                ordered_items.append(all_docs[item_id])
                seen_ids.add(item_id)
                
        # Append any remaining document items not referenced in spine
        for item_id, item in all_docs.items():
            if item_id not in seen_ids:
                ordered_items.append(item)
                seen_ids.add(item_id)
                
        return ordered_items

    def extract_chunks(self, item: Any) -> Tuple[BeautifulSoup, List[Tag]]:
        """
        Extracts translatable text nodes from a single EPUB HTML document item.
        Differentiates Block elements from Inline elements.
        Paragraphs containing inline tags (em, span, b, ruby) are preserved as whole blocks.
        Returns: (soup, list_of_nodes)
        """
        raw_content = item.get_content()
        soup = BeautifulSoup(raw_content, "html.parser")
        self._item_soups[item.get_id()] = (item, soup)

        nodes: List[Tag] = []
        
        # Traverse DOM looking for leaf block elements or text-bearing divs
        for tag in soup.find_all(True):
            if not isinstance(tag, Tag):
                continue

            tag_name = tag.name.lower()
            
            # Case 1: Standard block tags (p, h1-h6, blockquote, li, etc.)
            if tag_name in BLOCK_TAGS:
                # Ensure this block does not contain nested block-level children
                has_nested_block = any(
                    child.name and child.name.lower() in BLOCK_TAGS
                    for child in tag.find_all(True)
                )
                if not has_nested_block:
                    text = tag.get_text(strip=True)
                    if text and len(text) > 0:
                        nodes.append(tag)
                        
            # Case 2: Divs that contain direct text or inline elements without any block children
            elif tag_name == "div":
                # Skip outer div if it contains any child div elements to extract only leaf/innermost divs
                has_nested_div = any(
                    child.name and child.name.lower() == "div"
                    for child in tag.find_all(True)
                )
                if has_nested_div:
                    continue

                has_nested_block = any(
                    child.name and child.name.lower() in BLOCK_TAGS
                    for child in tag.find_all(True)
                )
                if not has_nested_block:
                    # Check if there is meaningful text
                    text = tag.get_text(strip=True)
                    if text and len(text) > 0:
                        nodes.append(tag)

        return soup, nodes

    def extract_text_nodes(self) -> List[Dict[str, Any]]:
        """
        Extracts all translatable text nodes across the entire EPUB in spine order.
        Returns a list of structured node records matching interface contracts.
        """
        extracted_nodes: List[Dict[str, Any]] = []
        items = self.get_html_items()
        
        for item in items:
            item_id = item.get_id()
            soup, nodes = self.extract_chunks(item)
            for idx, node in enumerate(nodes):
                inner_html = "".join(str(c) for c in node.contents)
                extracted_nodes.append({
                    "item_id": item_id,
                    "node_index": idx,
                    "tag": node.name,
                    "text": node.get_text(strip=True),
                    "inner_html": inner_html,
                    "node": node,
                    "item": item,
                    "soup": soup,
                })
                
        return extracted_nodes

    def update_node(self, node: Tag, translated_text_or_html: str) -> None:
        """
        Replaces the inner content of a DOM node while strictly preserving
        outer tag attributes (class, id, style) and parsing translated inline markup.
        Prevents accidental double-wrapping if the translation output included the outer tag.
        """
        if node is None:
            return

        cleaned_content = str(translated_text_or_html).strip()
        
        # Strip potential markdown code block wrappers (e.g. ```html ... ```)
        if cleaned_content.startswith("```"):
            lines = cleaned_content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned_content = "\n".join(lines).strip()

        # Parse replacement content into a BeautifulSoup fragment
        frag = BeautifulSoup(cleaned_content, "html.parser")
        
        # If the fragment contains a single root tag matching the node's tag, unwrap it
        frag_children = [c for c in frag.contents if not (isinstance(c, NavigableString) and not c.strip())]
        if len(frag_children) == 1 and isinstance(frag_children[0], Tag) and frag_children[0].name.lower() == node.name.lower():
            contents_to_insert = list(frag_children[0].contents)
        else:
            contents_to_insert = list(frag.contents)

        # Clear existing children of the node (keeps tag name and attributes intact)
        node.clear()

        # Insert new translated content (strings and inline tags)
        for child in contents_to_insert:
            node.append(child)

    def repack(self, output_path: str) -> str:
        """
        Synchronizes all modified document soups back to EPUB items and writes
        the repacked EPUB archive to output_path. Preserves all styles, images, and metadata.
        Returns the output_path.
        """
        # Sync modified soups back into the items
        for item_id, (item, soup) in self._item_soups.items():
            item.set_content(str(soup).encode("utf-8"))

        output_dir = os.path.dirname(os.path.abspath(output_path))
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        epub.write_epub(output_path, self.book, {})
        return output_path

    def save_book(self, output_path: str) -> str:
        """Backward-compatible alias for repack."""
        return self.repack(output_path)
