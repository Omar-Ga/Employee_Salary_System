from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
import arabic_reshaper
from bidi.algorithm import get_display
import os

class SalarySlipGenerator:
    def __init__(self):
        # A4 dimensions in points (1 point = 1/72 inch)
        self.page_width, self.page_height = A4
        # Each slip takes exactly half of A4 height
        self.slip_height = self.page_height / 2
        
        # Register Arabic font
        self.setup_arabic_font()
    
    def setup_arabic_font(self):
        """Register Arial Unicode font for Arabic text support"""
        font_path = os.path.join('fonts', 'ARIALUNI.TTF')
        arial_unicode = TTFont('ArialUnicode', font_path)
        pdfmetrics.registerFont(arial_unicode)
        self.arabic_font = 'ArialUnicode'  # Store font name for later use
    
    def generate_salary_slips(self, employees_data, output_path):
        """
        Generate PDF with salary slips, two per page
        
        Args:
            employees_data: List of employee dictionaries containing salary info
            output_path: Where to save the PDF file
        """
        # Create PDF canvas
        c = canvas.Canvas(output_path, pagesize=A4)
        
        # Process employees two at a time
        for i in range(0, len(employees_data), 2):
            # Top half
            if i < len(employees_data):
                self.draw_salary_slip(c, employees_data[i], is_top=True)
            
            # Bottom half
            if i + 1 < len(employees_data):
                self.draw_salary_slip(c, employees_data[i + 1], is_top=False)
            
            c.showPage()  # End the current page
        
        c.save()
    
    def draw_salary_slip(self, canvas, employee_data, is_top=True):
        """
        Draw a single salary slip on either top or bottom half of the page
        
        Args:
            canvas: ReportLab canvas object
            employee_data: Dictionary containing employee's salary information
            is_top: Boolean indicating if this slip goes on top half
        """
        # Calculate Y position (top or bottom half)
        y_start = self.page_height if is_top else self.slip_height
        
        # We'll implement the actual drawing here
        pass

    def format_arabic_text(self, text):
        """Helper function to handle Arabic text"""
        reshaped_text = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped_text)
        return bidi_text 