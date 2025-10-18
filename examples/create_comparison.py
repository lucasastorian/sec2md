"""
Generate a before/after comparison image for the README.

This script creates a side-by-side comparison of raw SEC HTML vs clean Markdown.
"""

from PIL import Image, ImageDraw, ImageFont
import textwrap


def create_comparison_image(
    raw_html: str,
    markdown: str,
    output_path: str = "comparison.png",
    width: int = 1200,
    height: int = 600
):
    """
    Create a side-by-side comparison image.

    Args:
        raw_html: Raw HTML snippet
        markdown: Converted Markdown snippet
        output_path: Where to save the image
        width: Image width in pixels
        height: Image height in pixels
    """
    # Create image with white background
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)

    # Try to use a monospace font, fall back to default
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Monaco.ttf", 14)
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except:
        font = ImageFont.load_default()
        title_font = ImageFont.load_default()

    # Colors
    bg_left = '#f8f8f8'  # Light gray for raw HTML side
    bg_right = '#ffffff'  # White for Markdown side
    border_color = '#e1e4e8'
    text_color = '#24292e'
    title_color = '#586069'

    # Draw backgrounds
    draw.rectangle([0, 0, width//2, height], fill=bg_left)
    draw.rectangle([width//2, 0, width, height], fill=bg_right)

    # Draw vertical separator
    draw.line([(width//2, 0), (width//2, height)], fill=border_color, width=2)

    # Draw titles
    draw.text((20, 20), "Raw SEC HTML", fill=title_color, font=title_font)
    draw.text((width//2 + 20, 20), "Clean Markdown", fill=title_color, font=title_font)

    # Wrap text
    left_text = textwrap.fill(raw_html, width=50)
    right_text = textwrap.fill(markdown, width=50)

    # Draw text
    draw.text((20, 60), left_text, fill=text_color, font=font)
    draw.text((width//2 + 20, 60), right_text, fill=text_color, font=font)

    # Save
    img.save(output_path)
    print(f"Saved comparison image to {output_path}")


if __name__ == "__main__":
    # Example: Table from Apple 10-K
    raw_html = """<table style="border-collapse:collapse;">
<tr><td style="position:absolute;left:0px;top:0px;">
<span style="font-family:Times New Roman;font-size:10pt;">
<us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax>
Net sales by category:</span></td></tr>
<tr><td style="position:absolute;left:0px;top:20px;">
<span>iPhone</span></td>
<td style="position:absolute;left:200px;top:20px;">
<span>$200,583</span></td></tr>
<tr><td style="position:absolute;left:0px;top:40px;">
<span>Mac</span></td>
<td style="position:absolute;left:200px;top:40px;">
<span>$29,357</span></td></tr>
</table>"""

    markdown = """**Net sales by category:**

| Product | Revenue (millions) |
|---------|-------------------|
| iPhone  | $200,583          |
| Mac     | $29,357           |"""

    create_comparison_image(raw_html, markdown, "examples/comparison.png")
