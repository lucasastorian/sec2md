"""
Generate a before/after comparison image for the README.

This script:
1. Extracts the first page from SEC HTML (between first two <hr> tags)
2. Converts it to clean Markdown using sec2md
3. Renders both to PNG images
4. Combines them side-by-side
"""

from edgar import Company, set_identity
import sec2md
import re

# Setup
set_identity("Your Name <you@example.com>")

# Get Apple's latest 10-K
print("Fetching Apple 10-K...")
company = Company('AAPL')
filing = company.get_filings(form="10-K").latest()
raw_html = filing.html()

# Extract first page (title page is BEFORE first <hr> tag)
print("Extracting first page (title page)...")
hr_pattern = r'<hr[^>]*?>'
matches = list(re.finditer(hr_pattern, raw_html, re.IGNORECASE))

if len(matches) >= 1:
    # First page is everything BEFORE the first <hr>
    first_page_html = raw_html[:matches[0].start()]
else:
    # Fallback if no <hr> tags found
    first_page_html = raw_html[:127000]

print(f"First page HTML length: {len(first_page_html)} chars")

# Convert to Markdown
print("Converting to Markdown...")
pages = sec2md.convert_to_markdown(raw_html, return_pages=True)
first_page_md = pages[0].content

print(f"First page Markdown length: {len(first_page_md)} chars")

# Now render both to images using Playwright
try:
    from playwright.sync_api import sync_playwright
    from PIL import Image
    import markdown

    # US Letter dimensions at 300 DPI: 8.5" x 11" = 2550 x 3300 pixels (higher quality)
    letter_width = 2550
    letter_height = 3300

    def render_to_image(html_content: str, output_path: str):
        """Render HTML to PNG using Playwright with US Letter viewport."""
        with sync_playwright() as p:
            browser = p.chromium.launch()
            # Use FULL US Letter width for viewport so content doesn't wrap weird
            page = browser.new_page(viewport={'width': letter_width, 'height': letter_height})
            page.set_content(html_content)
            # Take full page screenshot (captures all content, even if longer than viewport)
            page.screenshot(path=output_path, full_page=True)
            browser.close()

    # Wrap raw HTML in proper document (padding so content doesn't touch borders)
    # At 300 DPI, we need larger font sizes to match 150 DPI rendering
    # Use !important to override inline SEC HTML styles
    raw_html_doc = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Raw HTML</title>
        <style>
            body {{
                padding: 60px;
                font-family: Arial !important;
                background: white;
                margin: 0;
                overflow: hidden;
                height: {letter_height}px;
                box-sizing: border-box;
            }}
            * {{
                font-size: 24pt !important;
                line-height: 1.4 !important;
            }}
        </style>
    </head>
    <body>
        {first_page_html}
    </body>
    </html>
    """

    # Convert Markdown to HTML for rendering (padding so content doesn't touch borders)
    md_html = markdown.markdown(first_page_md, extensions=['tables'])
    md_html_doc = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Clean Markdown</title>
        <style>
            body {{
                padding: 60px;
                font-family: Arial;
                background: white;
                margin: 0;
                overflow: hidden;
                height: {letter_height}px;
                font-size: 28pt;
                line-height: 1.4;
                box-sizing: border-box;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 15px 0;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 16px;
                text-align: left;
                font-size: 24pt;
            }}
            th {{ background-color: #f2f2f2; font-weight: bold; }}
        </style>
    </head>
    <body>
        {md_html}
    </body>
    </html>
    """

    # Render both to images (each at full US Letter width)
    print("Rendering raw HTML to image...")
    render_to_image(raw_html_doc, "raw_html.png")

    print("Rendering clean Markdown to image...")
    render_to_image(md_html_doc, "clean_markdown.png")

    # Combine side-by-side with "two windows" design
    print("Combining images with borders and titles...")
    from PIL import ImageDraw, ImageFont

    img1 = Image.open("raw_html.png")
    img2 = Image.open("clean_markdown.png")

    # Truncate to letter height (since we set overflow:hidden in CSS, but just in case)
    img1 = img1.crop((0, 0, img1.width, min(img1.height, letter_height)))
    img2 = img2.crop((0, 0, img2.width, min(img2.height, letter_height)))

    # Scale down the images to 45% for smaller previews with even more padding
    scale = 0.45
    new_width = int(letter_width * scale)
    new_height = int(letter_height * scale)

    img1 = img1.resize((new_width, new_height), Image.Resampling.LANCZOS)
    img2 = img2.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Layout parameters (doubled for higher DPI)
    outer_padding = 160  # Even more padding around entire canvas
    gap = 120  # More space between the two "windows"
    border_radius = 32  # Larger rounded corners (airplane window style)
    border_width = 2
    title_height = 120  # More space for larger titles below

    # Calculate canvas size
    canvas_width = (outer_padding * 2) + (new_width * 2) + gap
    canvas_height = (outer_padding * 2) + new_height + title_height

    # Create canvas with medium gray background (like Mac Preview PDF viewer)
    canvas = Image.new('RGB', (canvas_width, canvas_height), '#8e8e93')
    draw = ImageDraw.Draw(canvas)

    # Helper function to draw rounded rectangle with border
    def draw_rounded_rect_with_border(draw, xy, radius, fill, border_color, border_width):
        x1, y1, x2, y2 = xy
        # Draw border (slightly larger)
        draw.rounded_rectangle(
            [x1 - border_width, y1 - border_width, x2 + border_width, y2 + border_width],
            radius=radius,
            fill=border_color
        )
        # Draw inner rectangle
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)

    # Position for left image (raw HTML)
    left_x = outer_padding
    left_y = outer_padding

    # Create rounded mask for clipping images
    from PIL import ImageDraw

    def create_rounded_mask(width, height, radius):
        """Create a rounded rectangle mask for clipping."""
        mask = Image.new('L', (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, width, height], radius=radius, fill=255)
        return mask

    # Create mask
    mask = create_rounded_mask(new_width, new_height, border_radius)

    # Draw background rectangles with borders first
    draw_rounded_rect_with_border(
        draw,
        [left_x, left_y, left_x + new_width, left_y + new_height],
        radius=border_radius,
        fill='white',
        border_color='#e5e7eb',
        border_width=border_width
    )

    # Paste left image with rounded mask
    canvas.paste(img1, (left_x, left_y), mask)

    # Position for right image (clean markdown)
    right_x = left_x + new_width + gap
    right_y = outer_padding

    # Draw background rectangle with border
    draw_rounded_rect_with_border(
        draw,
        [right_x, right_y, right_x + new_width, right_y + new_height],
        radius=border_radius,
        fill='white',
        border_color='#e5e7eb',
        border_width=border_width
    )

    # Paste right image with rounded mask
    canvas.paste(img2, (right_x, right_y), mask)

    # Add titles below each image
    try:
        # Try to load a nice font with larger size (doubled for higher DPI)
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
    except:
        font = ImageFont.load_default()

    # Title positions (centered below each image)
    left_title = "Raw SEC HTML"
    right_title = "Clean Markdown"

    title_y = left_y + new_height + 40

    # Get text bounding boxes for centering
    left_bbox = draw.textbbox((0, 0), left_title, font=font)
    left_text_width = left_bbox[2] - left_bbox[0]
    left_text_x = left_x + (new_width - left_text_width) // 2

    right_bbox = draw.textbbox((0, 0), right_title, font=font)
    right_text_width = right_bbox[2] - right_bbox[0]
    right_text_x = right_x + (new_width - right_text_width) // 2

    # Draw titles in white (to contrast with gray background)
    draw.text((left_text_x, title_y), left_title, fill='#ffffff', font=font)
    draw.text((right_text_x, title_y), right_title, fill='#ffffff', font=font)

    canvas.save("comparison.png")
    print("✅ Saved comparison.png")

    # Clean up temp files
    import os
    os.remove("raw_html.png")
    os.remove("clean_markdown.png")

    print("\n🎉 Done! Add to README with:")
    print("   ![Before/After](examples/comparison.png)")

except ImportError as e:
    print(f"⚠️  Missing dependency: {e}")
    print("\nInstall with:")
    print("   pip install playwright markdown pillow")
    print("   playwright install chromium")
    print("\nOr just screenshot the notebook outputs manually!")
