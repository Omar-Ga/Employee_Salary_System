from salary_slip_generator import SalarySlipGenerator
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black
from datetime import datetime
import arabic_reshaper
from bidi.algorithm import get_display
import sqlite3
import os
from PyPDF2 import PdfMerger
import glob

def get_employee_transactions(employee_id):
    """Get all transactions for an employee from the database"""
    conn = sqlite3.connect('employees.db')
    cursor = conn.cursor()
    
    # Get employee base data
    cursor.execute('''
        SELECT name, job_title, full_package
        FROM employees 
        WHERE id = ?
    ''', (employee_id,))
    emp_data = cursor.fetchone()
    
    if not emp_data:  # If employee not found
        conn.close()
        return None
        
    # Get transaction totals
    cursor.execute('''
        SELECT 
            SUM(CASE WHEN transaction_type = 'الاضافي' THEN amount ELSE 0 END) as overtime,
            SUM(CASE WHEN transaction_type = 'حافز' THEN amount ELSE 0 END) as bonus,
            SUM(CASE WHEN transaction_type = 'الخصم' THEN amount ELSE 0 END) as deductions,
            SUM(CASE WHEN transaction_type = 'السلف' THEN amount ELSE 0 END) as advance
        FROM transactions
        WHERE employee_id = ?
    ''', (employee_id,))
    trans_data = cursor.fetchone()
    
    conn.close()
    
    # Calculate final amounts
    full_package = emp_data[2]
    overtime = trans_data[0] or 0
    bonus = trans_data[1] or 0
    deductions = trans_data[2] or 0
    advance = trans_data[3] or 0
    net_amount = full_package + bonus + overtime - deductions - advance
    
    return {
        'name': emp_data[0],
        'department': emp_data[1],
        'date': datetime.now().strftime('%Y/%m/%d'),
        'full_package': full_package,
        'overtime': overtime,
        'bonus': bonus,
        'deductions': deductions,
        'advance': advance,
        'net_amount': net_amount
    }

def get_active_employees():
    """Get list of active employee IDs"""
    conn = sqlite3.connect('employees.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM employees WHERE status = "active" ORDER BY name')
    employee_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return employee_ids

def draw_signature_area(canvas, generator, is_top):
    """Draw signature line at the bottom of the slip"""
    # Calculate y position based on whether it's top or bottom half
    base_y = (A4[1] - 400) if is_top else (A4[1]/2 - 400)
    
    # Set font
    canvas.setFont(generator.arabic_font, 12)
    
    # Draw signature line
    line_width = 200
    line_x = A4[0] - 50 - line_width  # 50 points margin from right
    
    # Signature line
    canvas.line(line_x, base_y, line_x + line_width, base_y)
    sig_text = generator.format_arabic_text("التوقيع")
    canvas.drawRightString(line_x + line_width, base_y + 15, sig_text)

def draw_header(canvas, generator, employee_data, is_top):
    """Draw header section with employee info and date"""
    # Calculate starting y position
    y_start = A4[1] - 50 if is_top else (A4[1]/2) - 50
    
    # Format date in Arabic
    date_text = generator.format_arabic_text(f"التاريخ: {employee_data['date']}")
    name_text = generator.format_arabic_text(f"الاسم: {employee_data['name']}")
    dept_text = generator.format_arabic_text(f"القسم: {employee_data['department']}")
    
    # Set font
    canvas.setFont(generator.arabic_font, 14)
    
    # Draw text (right-aligned)
    x_margin = 50
    canvas.drawRightString(A4[0] - x_margin, y_start, date_text)
    canvas.drawRightString(A4[0] - x_margin, y_start - 20, name_text)
    canvas.drawRightString(A4[0] - x_margin, y_start - 40, dept_text)

def draw_slip(canvas, generator, employee_data, is_top):
    """Draw a complete salary slip on either top or bottom half of the page"""
    # Draw header first
    draw_header(canvas, generator, employee_data, is_top)
    
    # Calculate starting y position for financial details
    y_start = A4[1] - 150 if is_top else (A4[1]/2) - 150
    
    # Set font for table
    canvas.setFont(generator.arabic_font, 12)
    
    # Table configuration
    table_width = 400
    table_x = A4[0] - 50 - table_width  # 50 points margin from right
    row_height = 25
    col_widths = [250, 150]  # Label column, Value column
    
    # Draw table outline
    canvas.rect(table_x, y_start - (6 * row_height), table_width, 6 * row_height)  # Reduced height for 6 rows
    
    # Financial items with their values
    items = [
        ('الاضافي:', f"{employee_data['overtime']:,.2f}"),
        ('حافز:', f"{employee_data['bonus']:,.2f}"),
        ('الخصم:', f"{employee_data['deductions']:,.2f}"),
        ('السلف:', f"{employee_data['advance']:,.2f}"),
        ('اجمالي الراتب:', f"{employee_data['full_package']:,.2f}"),
        ('الصافي:', f"{employee_data['net_amount']:,.2f}")
    ]
    
    # Draw horizontal lines for each row
    for i in range(1, len(items)):
        y = y_start - (i * row_height)
        canvas.line(table_x, y, table_x + table_width, y)
    
    # Draw vertical line between label and value
    canvas.line(table_x + col_widths[0], y_start - (6 * row_height),  # Updated for 6 rows
                table_x + col_widths[0], y_start)
    
    # Fill in the table data
    for i, (label, value) in enumerate(items):
        y = y_start - (i * row_height) - (row_height * 0.6)  # Center text vertically in row
        
        # Draw label (right-aligned)
        label_text = generator.format_arabic_text(label)
        canvas.drawRightString(table_x + col_widths[0] - 10, y, label_text)
        
        # Draw value (center-aligned in its column)
        value_text = generator.format_arabic_text(f"{value} ج.م")
        value_width = canvas.stringWidth(value_text, generator.arabic_font, 12)
        value_x = table_x + col_widths[0] + (col_widths[1] - value_width) / 2
        canvas.drawString(value_x, y, value_text)
    
    # Add table title
    title_y = y_start + 20
    title_text = generator.format_arabic_text("تفاصيل الراتب")
    canvas.setFont(generator.arabic_font, 14)
    canvas.drawRightString(table_x + table_width, title_y, title_text)
    
    # Add signature area at the bottom
    draw_signature_area(canvas, generator, is_top)

def generate_salary_slips(employee_ids, output_path=None):
    """
    Generate PDF with two different employees per page
    
    Args:
        employee_ids: List of employee IDs to generate slips for
        output_path: Optional path for the final PDF. If None, generates a default name
    """
    if output_path is None:
        # Generate default filename with date
        date_str = datetime.now().strftime('%Y%m%d')
        output_path = f'salary_slips_{date_str}.pdf'
    
    generator = SalarySlipGenerator()
    temp_files = []
    
    try:
        # Process employees two at a time
        for i in range(0, len(employee_ids), 2):
            temp_file = f"temp_salary_slip_page_{i//2 + 1}.pdf"
            temp_files.append(temp_file)
            
            c = canvas.Canvas(temp_file, pagesize=A4)
            
            # Draw middle division line
            c.setStrokeColor(black)
            c.setDash(1, 2)
            c.line(0, A4[1]/2, A4[0], A4[1]/2)
            
            # Top half - first employee
            emp1_data = get_employee_transactions(employee_ids[i])
            if emp1_data:
                draw_slip(c, generator, emp1_data, True)
            
            # Bottom half - second employee (if exists)
            if i + 1 < len(employee_ids):
                emp2_data = get_employee_transactions(employee_ids[i + 1])
                if emp2_data:
                    draw_slip(c, generator, emp2_data, False)
            
            c.save()
        
        # Merge all temporary PDFs into final file
        merger = PdfMerger()
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                merger.append(temp_file)
        
        merger.write(output_path)
        merger.close()
        
        return output_path
        
    finally:
        # Cleanup temporary files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                print(f"Warning: Could not delete temporary file {temp_file}: {e}")

# Test function for standalone testing
def test_with_real_data():
    """Test function to generate salary slips for all active employees"""
    # Get all active employees
    employee_ids = get_active_employees()
    
    # Generate salary slips
    output_file = generate_salary_slips(employee_ids)
    print(f"Generated salary slips at: {output_file}")

# Only run the test if this file is executed directly
if __name__ == "__main__":
    test_with_real_data() 