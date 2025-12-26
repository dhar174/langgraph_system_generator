"""Professional PDF manuscript generation for print outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


class ManuscriptPDFGenerator:
    """Generates formatted PDF manuscripts with professional styling."""

    def __init__(
        self,
        page_size: tuple = letter,
        font_name: str = "Times-Roman",
        font_size: int = 12,
    ):
        """Initialize the PDF generator with default styling.

        Args:
            page_size: Page size tuple (width, height) in points. Defaults to letter (8.5x11).
            font_name: Font family for body text.
            font_size: Font size in points for body text.
        """
        self.page_size = page_size
        self.font_name = font_name
        self.font_size = font_size
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self) -> None:
        """Set up custom paragraph styles for the document."""
        # Chapter title style
        self.chapter_style = ParagraphStyle(
            "ChapterTitle",
            parent=self.styles["Heading1"],
            fontName=self.font_name.replace("-Roman", "-Bold"),
            fontSize=16,
            spaceAfter=30,
            spaceBefore=20,
            alignment=0,  # Left aligned
        )

        # Section heading style
        self.section_style = ParagraphStyle(
            "SectionHeading",
            parent=self.styles["Heading2"],
            fontName=self.font_name.replace("-Roman", "-Bold"),
            fontSize=14,
            spaceAfter=20,
            spaceBefore=15,
        )

        # Body text style
        self.body_style = ParagraphStyle(
            "CustomBody",
            parent=self.styles["BodyText"],
            fontName=self.font_name,
            fontSize=self.font_size,
            leading=self.font_size * 1.5,  # Line height
            spaceAfter=6,
            alignment=4,  # Justified
        )

        # Code block style
        self.code_style = ParagraphStyle(
            "CodeBlock",
            parent=self.styles["Code"],
            fontName="Courier",
            fontSize=10,
            leftIndent=0.5 * inch,
            spaceAfter=12,
            spaceBefore=6,
            backColor="#f0f0f0",
        )

    def create_manuscript(
        self,
        title: str,
        chapters: Sequence[Dict[str, Any]],
        output_path: str | Path,
        author: str | None = None,
        include_title_page: bool = True,
    ) -> str:
        """Generate a print-ready PDF manuscript.

        Args:
            title: Manuscript title.
            chapters: List of chapter dictionaries with 'title' and 'content' keys.
                     Content can be a string or list of strings/paragraphs.
            output_path: Destination path for the PDF file.
            author: Optional author name.
            include_title_page: Whether to include a formatted title page.

        Returns:
            Path to the created PDF file.
        """
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Create document with margins
        doc = SimpleDocTemplate(
            str(target),
            pagesize=self.page_size,
            rightMargin=72,  # 1 inch
            leftMargin=72,
            topMargin=72,
            bottomMargin=72,
        )

        story: List[Any] = []

        # Add title page if requested
        if include_title_page:
            self._add_title_page(story, title, author)

        # Add chapters
        for chapter in chapters:
            self._add_chapter(story, chapter)

        # Build the PDF
        doc.build(story)
        return str(target)

    def _add_title_page(
        self, story: List[Any], title: str, author: str | None = None
    ) -> None:
        """Add a formatted title page to the story.

        Args:
            story: The story list to append to.
            title: The manuscript title.
            author: Optional author name.
        """
        # Title page style
        title_style = ParagraphStyle(
            "TitlePage",
            parent=self.styles["Title"],
            fontName=self.font_name.replace("-Roman", "-Bold"),
            fontSize=24,
            alignment=1,  # Center aligned
            spaceAfter=30,
        )

        author_style = ParagraphStyle(
            "AuthorName",
            parent=self.styles["Normal"],
            fontName=self.font_name,
            fontSize=14,
            alignment=1,  # Center aligned
        )

        # Add vertical spacing
        story.append(Spacer(1, 2 * inch))

        # Add title
        story.append(Paragraph(title, title_style))

        # Add spacing
        story.append(Spacer(1, 0.5 * inch))

        # Add author if provided
        if author:
            story.append(Paragraph(f"by {author}", author_style))

        # Page break after title page
        story.append(PageBreak())

    def _add_chapter(self, story: List[Any], chapter: Dict[str, Any]) -> None:
        """Add a chapter to the story.

        Args:
            story: The story list to append to.
            chapter: Dictionary with 'title' and 'content' keys.
        """
        chapter_title = chapter.get("title", "Untitled Chapter")
        chapter_content = chapter.get("content", [])

        # Add chapter title
        story.append(Paragraph(chapter_title, self.chapter_style))
        story.append(Spacer(1, 0.2 * inch))

        # Add chapter content
        if isinstance(chapter_content, str):
            # Single string content - split by paragraphs
            for paragraph in chapter_content.split("\n\n"):
                if paragraph.strip():
                    story.append(Paragraph(paragraph.strip(), self.body_style))
                    story.append(Spacer(1, 0.1 * inch))
        elif isinstance(chapter_content, (list, tuple)):
            # List of paragraphs or structured content
            for item in chapter_content:
                if isinstance(item, dict):
                    # Structured content with sections
                    section_title = item.get("heading")
                    section_text = item.get("text", "")

                    if section_title:
                        story.append(Paragraph(section_title, self.section_style))
                        story.append(Spacer(1, 0.1 * inch))

                    if section_text:
                        story.append(Paragraph(section_text, self.body_style))
                        story.append(Spacer(1, 0.1 * inch))
                else:
                    # Plain paragraph text
                    if item and str(item).strip():
                        story.append(Paragraph(str(item).strip(), self.body_style))
                        story.append(Spacer(1, 0.1 * inch))

        # Page break after chapter
        story.append(PageBreak())

    def create_notebook_manuscript(
        self,
        notebook_cells: Sequence[Dict[str, Any]],
        output_path: str | Path,
        title: str | None = None,
        author: str | None = None,
    ) -> str:
        """Create a manuscript PDF from notebook cells.

        Args:
            notebook_cells: List of cell dictionaries with 'cell_type', 'content', and optional 'section'.
            output_path: Destination path for the PDF file.
            title: Optional manuscript title.
            author: Optional author name.

        Returns:
            Path to the created PDF file.
        """
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(target),
            pagesize=self.page_size,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72,
        )

        story: List[Any] = []

        # Add title page if title provided
        if title:
            self._add_title_page(story, title, author)

        current_section = None

        for cell in notebook_cells:
            cell_type = cell.get("cell_type", "code")
            content = cell.get("content", "")
            section = cell.get("section")

            # Add section heading if changed
            if section and section != current_section:
                section_title = section.replace("_", " ").title()
                story.append(Paragraph(section_title, self.chapter_style))
                story.append(Spacer(1, 0.2 * inch))
                current_section = section

            # Process cell content
            if cell_type == "markdown" and content.strip():
                # Parse markdown for basic formatting
                for line in content.split("\n"):
                    line = line.strip()
                    if not line:
                        story.append(Spacer(1, 0.1 * inch))
                        continue

                    # Handle headings
                    if line.startswith("### "):
                        subsection_style = ParagraphStyle(
                            "SubsectionHeading",
                            parent=self.styles["Heading3"],
                            fontSize=12,
                            spaceAfter=10,
                            spaceBefore=10,
                        )
                        story.append(Paragraph(line[4:], subsection_style))
                    elif line.startswith("## "):
                        story.append(Paragraph(line[3:], self.section_style))
                    elif line.startswith("# "):
                        story.append(Paragraph(line[2:], self.chapter_style))
                    else:
                        story.append(Paragraph(line, self.body_style))

            elif cell_type == "code" and content.strip():
                # Add code as preformatted block
                # Escape special characters for reportlab
                safe_content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                code_para = Paragraph(
                    f"<pre><font face='Courier' size='9'>{safe_content}</font></pre>",
                    self.code_style,
                )
                story.append(code_para)
                story.append(Spacer(1, 0.1 * inch))

        # Build the PDF
        doc.build(story)
        return str(target)
