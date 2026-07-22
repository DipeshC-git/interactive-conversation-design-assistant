"""
pdf_processor.py — Deterministic PDF ↔ image conversion and structural tag injection.

Responsibilities
----------------
1. render_pdf_to_images()  — PDF bytes → list of PIL Images (one per page).
2. inject_tag_tree()       — Validated TagTree list → PDF bytes with a
                             PDF/UA-compliant Structural Parent Tree written in.

All pixel math and binary manipulation live here; the AI pipeline never touches
coordinates or file I/O directly (.bobrules: "Deterministic Overrides").

PyMuPDF tag injection strategy (Fix #1)
----------------------------------------
PyMuPDF does not expose a single high-level API for writing a full PDF structure
tree from Python objects. The correct approach is:

  1. Rebuild the document from scratch as a fitz.Story (rich, tagged HTML→PDF) —
     best for documents where we control all content.
  2. For remediation of an *existing* PDF (our case), we annotate the existing
     content stream with marked-content sequences using low-level PDF operators
     injected via page.insert_font / page.get_contents + page.set_contents,
     then register each marked-content item in the document's structure tree
     via fitz.Document PDF object manipulation.

We use approach 2: build the StructTreeRoot PDF dictionary programmatically and
inject /MCID marked-content operators into each page content stream.
"""

from __future__ import annotations

import io
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF ≥ 1.24
from pdf2image import convert_from_bytes
from PIL import Image

from schemas import PdfTag, TagNode, TagTree

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tag name → PDF role map (ISO 32000-2 standard structure types)
# ---------------------------------------------------------------------------
_ROLE_MAP: dict[PdfTag, str] = {
    PdfTag.H1:       "H1",
    PdfTag.H2:       "H2",
    PdfTag.H3:       "H3",
    PdfTag.H4:       "H4",
    PdfTag.H5:       "H5",
    PdfTag.H6:       "H6",
    PdfTag.P:        "P",
    PdfTag.L:        "L",
    PdfTag.LI:       "LI",
    PdfTag.LINK:     "Link",
    PdfTag.TABLE:    "Table",
    PdfTag.TR:       "TR",
    PdfTag.TH:       "TH",
    PdfTag.TD:       "TD",
    PdfTag.FIGURE:   "Figure",
    PdfTag.ARTIFACT: "Artifact",
}


# ---------------------------------------------------------------------------
# Stage 1 — PDF → PIL images
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Poppler binary path resolution
# ---------------------------------------------------------------------------

def _find_poppler_path() -> Optional[str]:
    """
    Locate the Poppler bin/ directory.

    Search order:
      1. POPPLER_PATH environment variable (explicit override).
      2. A 'bin/' folder co-located with this source file (the local
         playground/bin/ layout used in development).
      3. System PATH (Poppler installed system-wide).

    Returns the path string if a valid Poppler binary directory is found,
    or None if Poppler should be left to pdf2image's default PATH lookup.
    """
    # 1. Explicit env override
    env_path = os.environ.get("POPPLER_PATH", "").strip()
    if env_path and Path(env_path, "pdftoppm.exe").exists():
        logger.info("Using Poppler from POPPLER_PATH env: %s", env_path)
        return env_path

    # 2. Co-located bin/ folder (playground/bin/pdftoppm.exe)
    local_bin = Path(__file__).parent / "bin"
    if (local_bin / "pdftoppm.exe").exists():
        logger.info("Using co-located Poppler: %s", local_bin)
        return str(local_bin)

    # 3. Let pdf2image find it on PATH
    logger.debug("Poppler not found locally; relying on system PATH.")
    return None


_POPPLER_PATH: Optional[str] = _find_poppler_path()


def check_poppler_available() -> bool:
    """Return True if Poppler is reachable (used by startup health check)."""
    return _POPPLER_PATH is not None or _system_poppler_on_path()


def _system_poppler_on_path() -> bool:
    """Check if pdftoppm is available on the system PATH."""
    import shutil
    return shutil.which("pdftoppm") is not None


def render_pdf_to_images(
    pdf_bytes: bytes,
    dpi: int = 200,
    fmt: str = "PNG",
) -> list[Image.Image]:
    """
    Convert every page of a PDF into a high-resolution PIL Image.

    Parameters
    ----------
    pdf_bytes:
        Raw PDF file content.
    dpi:
        Render resolution. 200 dpi is sufficient for multimodal vision models;
        raise to 300 for documents with small print or dense tables.
    fmt:
        Pillow-compatible image format passed to pdf2image.

    Returns
    -------
    list[Image.Image]
        One image per page, in page order (index 0 = page 1).
    """
    images: list[Image.Image] = convert_from_bytes(
        pdf_bytes,
        dpi=dpi,
        fmt=fmt,
        thread_count=4,
        poppler_path=_POPPLER_PATH,
    )
    logger.info("Rendered %d page(s) at %d dpi.", len(images), dpi)
    return images


def image_to_bytes(image: Image.Image, fmt: str = "PNG") -> bytes:
    """Serialise a PIL Image to raw bytes for sending to an LLM vision API."""
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Stage 4 — validated TagTree list → tagged PDF bytes
# ---------------------------------------------------------------------------

def inject_tag_tree(
    pdf_bytes: bytes,
    tag_trees: list[TagTree],
    title: Optional[str] = None,
    language: str = "en",
) -> bytes:
    """
    Write a PDF/UA-compliant Structural Parent Tree into the document binary.

    Strategy
    --------
    We build a StructTreeRoot PDF dictionary and attach StructElem objects for
    every non-artifact TagNode. Each node is linked to the page via its MCID
    (marked content identifier). Artifact nodes are wrapped in marked-content
    operators /Artifact BMC … EMC so screen readers skip them.

    Parameters
    ----------
    pdf_bytes:
        Original (untagged or partially tagged) PDF content.
    tag_trees:
        One TagTree per page, in ascending page order.
    title:
        Document title written into the PDF metadata (required for PDF/UA).
    language:
        BCP-47 language tag written into the document catalogue.

    Returns
    -------
    bytes
        Fully tagged PDF bytes ready for download.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    # ── Mandatory PDF/UA document-level metadata ──────────────────────────
    doc.set_language(language)
    if title:
        doc.set_metadata({"title": title})
    doc.set_markinfo({"Marked": True})

    # ── Build StructTreeRoot + ParentTree NumberTree in the PDF catalog ───
    # ParentTree maps each MCID to its owning StructElem so PDF readers can
    # walk from a marked-content item back up to the structure tree.
    # We collect (mcid → struct_elem_xref) pairs during page processing and
    # write the NumberTree after all pages are done.
    catalog_xref = doc.pdf_catalog()

    # Allocate the ParentTree NumberTree object (body filled in after pages).
    parent_tree_xref = doc.get_new_xref()

    # Allocate the StructTreeRoot.
    struct_root_xref = doc.get_new_xref()
    doc.update_object(
        struct_root_xref,
        (
            f"<<\n"
            f"  /Type /StructTreeRoot\n"
            f"  /ParentTree {parent_tree_xref} 0 R\n"
            f"  /ParentTreeNextKey 0\n"
            f">>"
        ),
    )
    # Point the catalog at our new StructTreeRoot.
    doc.xref_set_key(catalog_xref, "StructTreeRoot", f"{struct_root_xref} 0 R")

    trees_by_page: dict[int, TagTree] = {t.page_number: t for t in tag_trees}
    mcid_counter: list[int] = [0]  # mutable int shared across recursive calls
    # Collects (mcid, struct_elem_xref) for the ParentTree NumberTree.
    parent_tree_nums: list[tuple[int, int]] = []

    for page_index in range(len(doc)):
        page_number = page_index + 1
        page = doc[page_index]
        tree = trees_by_page.get(page_number)
        if tree is None:
            logger.warning(
                "No TagTree for page %d — skipping structural injection.", page_number
            )
            continue
        _inject_page_structure(
            doc, page, tree, struct_root_xref, mcid_counter, parent_tree_nums
        )

    # ── Write the ParentTree NumberTree now that all MCIDs are known ──────
    # Format: << /Nums [ mcid structElem_xref ... ] >>
    nums_entries: list[str] = []
    for mcid, elem_xref in sorted(parent_tree_nums):
        nums_entries.append(f"{mcid} {elem_xref} 0 R")
    nums_array = " ".join(nums_entries)
    doc.update_object(
        parent_tree_xref,
        f"<<\n  /Nums [ {nums_array} ]\n>>",
    )
    # Update ParentTreeNextKey to one past the highest MCID used.
    next_key = mcid_counter[0]
    doc.xref_set_key(struct_root_xref, "ParentTreeNextKey", str(next_key))

    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True, clean=True)
    doc.close()
    return buf.getvalue()


def _inject_page_structure(
    doc: fitz.Document,
    page: fitz.Page,
    tree: TagTree,
    struct_root_xref: int,
    mcid_counter: list[int],
    parent_tree_nums: list[tuple[int, int]],
) -> None:
    """
    Inject marked-content operators into the page content stream and register
    corresponding StructElem PDF objects for every node in the TagTree.

    Artifact nodes emit  /Artifact BMC … EMC  (no StructElem entry).
    All other nodes emit  /tag_name <</MCID N>> BDC … EMC  and get a
    StructElem linked back to the page and its true parent StructElem
    (or the StructTreeRoot for top-level nodes).

    The parent_tree_nums list is extended with (mcid, struct_elem_xref) pairs
    so the caller can build the PDF ParentTree NumberTree after all pages.
    """
    mc_operations: list[str] = []  # PDF content stream fragments to append

    def _walk(node: TagNode, parent_xref: int) -> int:
        """
        Recursively process a node.

        Parameters
        ----------
        node        : the TagNode to process
        parent_xref : xref of the enclosing StructElem (or StructTreeRoot for
                      top-level nodes)

        Returns
        -------
        The xref of the StructElem created for this node (or 0 for artifacts).
        """
        role = _ROLE_MAP.get(node.tag, "P")

        if node.is_artifact:
            # Artifact: wrap any text in /Artifact marked-content — no structure entry.
            mc_operations.append("/Artifact BMC")
            if node.content:
                _append_text_op(mc_operations, node.content)
            mc_operations.append("EMC")
            # Recurse into children (e.g. artifact spans within a footer).
            for child in node.children:
                _walk(child, parent_xref)
            return 0

        mcid = mcid_counter[0]
        mcid_counter[0] += 1

        # Open a marked-content sequence for this structure element.
        mc_operations.append(f"/{role} <</MCID {mcid}>> BDC")

        if node.content:
            _append_text_op(mc_operations, node.content)

        # Allocate a StructElem PDF object — parent points to the enclosing
        # node (or StructTreeRoot for top-level), giving a proper nested tree.
        alt_entry = f"\n  /Alt ({_pdf_escape(node.alt_text)})" if node.alt_text else ""
        struct_elem_xref = doc.get_new_xref()
        # Temporarily write without /K (kids) — filled in after children.
        doc.update_object(
            struct_elem_xref,
            (
                f"<<\n"
                f"  /Type /StructElem\n"
                f"  /S /{role}\n"
                f"  /P {parent_xref} 0 R\n"
                f"  /Pg {page.xref} 0 R\n"
                f"  /MCID {mcid}"
                f"{alt_entry}\n"
                f">>"
            ),
        )
        # Record in ParentTree so PDF readers can resolve MCID → StructElem.
        parent_tree_nums.append((mcid, struct_elem_xref))

        # Process children, collecting their xrefs for the /K array.
        child_xrefs: list[int] = []
        for child in node.children:
            child_xref = _walk(child, struct_elem_xref)
            if child_xref:
                child_xrefs.append(child_xref)

        # Patch the /K (kids) entry now that all children are written.
        if child_xrefs:
            kids_str = " ".join(f"{x} 0 R" for x in child_xrefs)
            doc.xref_set_key(struct_elem_xref, "K", f"[ {kids_str} ]")

        mc_operations.append("EMC")
        return struct_elem_xref

    # Process all root-level nodes; their parent is the StructTreeRoot.
    root_child_xrefs: list[int] = []
    for root_node in tree.nodes:
        xref = _walk(root_node, struct_root_xref)
        if xref:
            root_child_xrefs.append(xref)

    # Register this page's top-level StructElems as kids of the StructTreeRoot.
    if root_child_xrefs:
        # Append to any existing /K on the StructTreeRoot (multi-page support).
        existing_k = doc.xref_get_key(struct_root_xref, "K")
        if existing_k and existing_k[0] != "null":
            # Already has kids — extend the array.
            existing_refs = existing_k[1].strip("[]").split()
            all_refs = existing_refs + [f"{x} 0 R" for x in root_child_xrefs]
        else:
            all_refs = [f"{x} 0 R" for x in root_child_xrefs]
        kids_str = " ".join(all_refs)
        doc.xref_set_key(struct_root_xref, "K", f"[ {kids_str} ]")

    # Append all marked-content operators to the existing page content stream.
    if mc_operations:
        existing = page.read_contents()
        appended = existing + b"\n" + "\n".join(mc_operations).encode("latin-1")
        page.set_contents(appended)


def _append_text_op(ops: list[str], text: str) -> None:
    """
    Append minimal PDF text-show operators for a string.
    Uses BT/ET block with Tj. The text is shown at the page origin (0,0);
    absolute positioning is handled by the existing content stream baseline.
    Real coordinates come from the original document — we are annotating
    structure, not re-flowing text.
    """
    escaped = _pdf_escape(text)
    ops.extend(["BT", f"({escaped}) Tj", "ET"])


def _pdf_escape(text: Optional[str]) -> str:
    """Escape a string for safe embedding inside a PDF literal string."""
    if not text:
        return ""
    return (
        text
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
