import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, Menu, messagebox
import os
import shutil
import sqlite3
from datetime import datetime
import pandas as pd
import logging
from access_control import AccessControl
import openpyxl
import sys # Added for sys.exit()
from app_lock import ApplicationLock # Added for concurrency control

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Changed level to INFO for more detail

class EmployeeManager(ctk.CTk):
    def __init__(self, *args, **kwargs):
        # --- Application Lock Check ---
        # This must happen before any significant initialization, especially GUI.
        self.app_lock = ApplicationLock()
        if not self.app_lock.acquire():
            # Initialize minimal tkinter components just to show the error message
            try:
                root = tk.Tk()
                root.withdraw() # Hide the main tkinter window
                messagebox.showerror("Application In Use", "Another user is currently running the application.\nPlease try again later.")
                root.destroy()
            except Exception as e:
                # Fallback if GUI elements fail (e.g., no display)
                logging.error(f"Failed to show messagebox: {e}")
                print("ERROR: Another user is currently running the application.", file=sys.stderr)
            sys.exit(1) # Exit if lock not acquired
        # --- End Application Lock Check ---

        # Check access before initializing (Original time-based check)
        access_control = AccessControl()
        if not access_control.check_access():
            # Ensure lock is released if time check fails after lock acquisition
            logging.warning("Time-based access check failed after acquiring lock. Releasing lock.")
            self.app_lock.release()
            # Potentially show a message here too, depending on desired behavior
            # messagebox.showerror("Access Denied", "Time limit exceeded or NTP check failed.") # Optional
            sys.exit()

        super().__init__(*args, **kwargs)






        # Initialize database connection
        self.db_connection = sqlite3.connect("employees.db")
        self.db_cursor = self.db_connection.cursor()
        self.create_db_tables()

        # Add this after database connection is established
        self.migrate_bonus_transactions()

        # Set initial size
        width = 1200
        height = 800
        
        # Calculate position for center of screen
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        
        # Set geometry with calculated position
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        ctk.set_appearance_mode("light")
        
        self.employees = []
        self.job_titles = []
        self.filtered_employees = []
        
        self.create_widgets()
        self.load_job_titles()
        self.load_employee_data()
        
        # Set default view to Active
        self.active_view = True

        # Schedule setting to full screen after a short delay
        self.after(100, self.set_fullscreen)

        # Handle application closure
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def migrate_bonus_transactions(self):
        """Migrate old bonus transaction names to new format"""
        try:
            self.db_cursor.execute('''
                UPDATE transactions 
                SET transaction_type = 'حافز' 
                WHERE transaction_type = 'المكافئه'
            ''')
            self.db_connection.commit()
        except sqlite3.Error as e:
            print(f"Migration error: {e}")

    def on_closing(self):
        """Handle application closure by releasing the lock, closing DB, and destroying windows."""
        logging.info("Starting application shutdown sequence...")
        try:
            # Close all Toplevel windows if they exist
            logging.info("Closing Toplevel windows...")
            for window_attr in ['job_title_window', 'new_window', 'edit_window']:
                if hasattr(self, window_attr):
                    window = getattr(self, window_attr)
                    if window and window.winfo_exists():
                        try:
                            window.destroy()
                            logging.info(f"Destroyed window: {window_attr}")
                        except Exception as win_e:
                            logging.error(f"Error destroying window {window_attr}: {win_e}")

            # Close the database connection
            logging.info("Closing database connection...")
            if hasattr(self, 'db_connection') and self.db_connection:
                try:
                    self.db_connection.close()
                    logging.info("Database connection closed successfully.")
                except Exception as db_e:
                    logging.error(f"Error closing database connection: {db_e}")
            else:
                logging.warning("Database connection attribute not found or already closed.")

        except Exception as e:
            # Catch errors during the main shutdown steps (closing windows/DB)
            logging.error(f"Error during main shutdown sequence (before finally block): {e}")
            # Avoid showing messagebox here as the main window might be unstable
        finally:
            # --- Critical: Release the application lock ---
            logging.info("Entering finally block for shutdown...")
            if hasattr(self, 'app_lock'):
                logging.info("Releasing application lock...")
                try:
                    self.app_lock.release()
                    logging.info("Application lock released successfully.")
                except Exception as lock_e:
                    logging.error(f"Error releasing application lock: {lock_e}")
            else:
                logging.warning("app_lock attribute not found during on_closing. Lock might not have been acquired or already released.")
            # --- End Lock Release ---

            # Now destroy the main application window
            logging.info("Destroying main application window...")
            try:
                self.destroy()
                logging.info("Main application window destroyed.")
            except Exception as destroy_e:
                logging.error(f"Error destroying main application window: {destroy_e}")

    def set_fullscreen(self):
        self.state('zoomed')  # For Windows


    # same centering function only used for the other windows
    def center_window(self, width, height, window=None):
        if window is None:
            window = self
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        scale_factor = window._get_window_scaling()
        x = int(((screen_width/2) - (width/2)) * scale_factor)
        y = int(((screen_height/2) - (height/1.5)) * scale_factor)
        window.geometry(f"{width}x{height}+{x}+{y}")
    
    def create_db_tables(self):
        # Create the employees table if it doesn't exist
        self.db_cursor.execute('''CREATE TABLE IF NOT EXISTS employees (
                                    id INTEGER PRIMARY KEY,
                                    name TEXT,
                                    id_number TEXT,
                                    phone TEXT,
                                    salary REAL,
                                    job_title TEXT,
                                    job TEXT,
                                    notes TEXT,
                                    status TEXT DEFAULT 'active',
                                    performance INTEGER DEFAULT 10,
                                    dedication INTEGER DEFAULT 10,
                                    responsibility INTEGER DEFAULT 10,
                                    full_package REAL
                                )''')

        # Check if the working_hours column exists, if not, add it
        self.db_cursor.execute("PRAGMA table_info(employees)")
        columns = [column[1] for column in self.db_cursor.fetchall()]
        if 'working_hours' not in columns:
            self.db_cursor.execute('''ALTER TABLE employees ADD COLUMN working_hours INTEGER DEFAULT 270''')

        # Create the job_titles table if it doesn't exist
        self.db_cursor.execute('''CREATE TABLE IF NOT EXISTS job_titles (
                                    id INTEGER PRIMARY KEY,
                                    title TEXT UNIQUE)''')

        # Create the transactions table if it doesn't exist
        self.db_cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
                                    id INTEGER PRIMARY KEY,
                                    employee_id INTEGER,
                                    transaction_type TEXT,
                                    amount REAL,
                                    FOREIGN KEY (employee_id) REFERENCES employees (id))''')

        self.db_connection.commit()
    
    def create_widgets(self):
        self.create_menu_bar()
        self.create_main_frame()
        self.create_sidebar()
        self.create_content_area()
    
    def create_menu_bar(self):
        menu_bar = Menu(self)
        self.config(menu=menu_bar)
        
        file_menu = Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label="ملف", menu=file_menu)
        
        file_menu.add_command(label=" إضافه اداره ", command=self.add_job_title_window)
        file_menu.add_separator()
    
    def create_main_frame(self):
        self.main_frame = ctk.CTkFrame(self, fg_color="gray90")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
    
    def create_sidebar(self):
        self.sidebar = ctk.CTkFrame(self.main_frame, width=300, corner_radius=0, fg_color=("gray86", "gray17"))
        self.sidebar.pack(side="left", fill="y", padx=0, pady=0)
        
        # Create a main container for all sidebar elements
        sidebar_container = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        sidebar_container.pack(fill="both", expand=True)
        
        # Top section (add button, search, filter)
        top_section = ctk.CTkFrame(sidebar_container, corner_radius=0, fg_color="transparent")
        top_section.pack(fill="x", padx=0, pady=(20, 10))
        
        self.add_button = ctk.CTkLabel(
            top_section,
            text="+",
            font=("Arial", 25, "bold"),
            text_color="white",
            fg_color="#1f6aa5",
            corner_radius=20,
            width=40,
            height=40
        )
        self.add_button.pack(side="right", padx=(10, 20))
        self.add_button.bind("<Button-1>", self.add_employee)
        
        # Create a frame to hold the search bar and filter button
        search_frame = ctk.CTkFrame(top_section, corner_radius=5, fg_color=("gray75", "gray25"))
        search_frame.pack(side="right", fill="x", expand=True, padx=(20, 0))
        
        # Add search bar
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="بحث...", 
                                         width=200, textvariable=self.search_var,
                                         border_width=0, fg_color="transparent",
                                         font=("Arial", 17, "bold"))
        self.search_entry.pack(side="right", padx=(0, 5), fill="x", expand=True)
        
        # Remove the trace and add Enter binding instead
        self.search_entry.bind("<Return>", self.on_search_enter)
        
        # Add filter button inside the search frame
        self.filter_button = ctk.CTkButton(search_frame, text="⋮", width=30, height=30,
                                           corner_radius=0, fg_color="transparent",
                                           hover_color=("gray70", "gray30"),
                                           command=self.show_filter_menu,
                                           font=("Arial", 17, "bold"))
        self.filter_button.pack(side="left")
        
        # Middle section (scrollable employee list)
        self.employee_frame = ctk.CTkFrame(sidebar_container, corner_radius=0)
        self.employee_frame.pack(fill="both", expand=True, pady=(10, 10))
        
        # Create a scrollable frame for the employee list
        self.scrollable_frame = ctk.CTkScrollableFrame(self.employee_frame, corner_radius=0)
        self.scrollable_frame.pack(fill="both", expand=True)
        
        # Create a frame inside the scrollable frame to hold the employee flyers
        self.flyer_container = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
        self.flyer_container.pack(fill="both", expand=True)
        
        # Bind mousewheel event to the scrollable frame
        self.scrollable_frame.bind("<MouseWheel>", self.on_mousewheel)
        
        # Bottom section (Active and Inactive buttons)
        bottom_section = ctk.CTkFrame(self.sidebar, corner_radius=0, fg_color="transparent")
        bottom_section.pack(fill="x", padx=10, pady=10)
        
        self.active_view = True  # Track current view
        
        self.active_button = ctk.CTkButton(
            bottom_section,
            text="نشط",
            command=self.show_active_employees,
            fg_color="#007acc",
            hover_color="#005f99",
            width=130, height=40,
            font=("Arial", 21, "bold")
        )
        self.active_button.pack(side="right", padx=(5, 0), pady=5)
        
        self.inactive_button = ctk.CTkButton(
            bottom_section,
            text="غير نشط",
            command=self.show_inactive_employees,
            fg_color="red",
            hover_color="darkred",
            width=200, height=40,
            font=("Arial", 21, "bold")
        )
        self.inactive_button.pack(side="right", padx=(0, 5))
    
    def create_content_area(self):
        self.content_area = ctk.CTkFrame(self.main_frame)
        self.content_area.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        self.inner_content = ctk.CTkFrame(self.content_area, fg_color=("gray80", "gray20"))
        self.inner_content.pack(fill=tk.BOTH, expand=True)
        
        self.placeholder = ctk.CTkLabel(
            self.inner_content, 
            text="اختر موظف", 
            font=("Arial", 53, "bold"),  
            text_color=("gray70", "gray30")
        )
        self.placeholder.pack(expand=True)
        
        self.details_frame = None  # Placeholder for employee details frame
    
    def add_job_title_window(self):
        self.job_title_window = ctk.CTkToplevel(self)
        self.job_title_window.title("إضافة مسمى وظيفي")
        self.center_window(300, 550, self.job_title_window)
        self.job_title_window.configure(bg="#f0f0f0")  # Light gray
        self.job_title_window.grab_set()

        label = ctk.CTkLabel(self.job_title_window, text="أدخل الاداره :", font=("Arial", 19, "bold"), text_color="black", justify="center")
        label.pack(pady=8, anchor="center")

        self.entry_job_title = ctk.CTkEntry(self.job_title_window, placeholder_text="الاداره ", font=("Arial", 17, "bold"))
        self.entry_job_title.pack(pady=8, anchor="center")

        save_button = ctk.CTkButton(self.job_title_window, text="حفظ", command=self.save_job_title, fg_color="#007acc", font=("Arial", 17, "bold"))
        save_button.pack(pady=8, anchor="center")

        # Frame to hold the listbox and scrollbar
        listbox_frame = ctk.CTkFrame(self.job_title_window, fg_color="transparent")
        listbox_frame.pack(pady=8, fill=tk.BOTH, expand=True)

        self.job_title_listbox = tk.Listbox(
            listbox_frame,
            font=("Arial", 17, "bold"),
            justify="center",
            bg="white",
            fg="black",
            selectbackground="#c0c0c0",
            selectforeground="black",
            activestyle="none"
        )
        self.job_title_listbox.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(listbox_frame, orient="vertical", command=self.job_title_listbox.yview)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)

        self.job_title_listbox.config(yscrollcommand=scrollbar.set)

        self.refresh_job_title_listbox()

        delete_button = ctk.CTkButton(self.job_title_window, text="حذف", command=self.delete_job_title, fg_color="red", font=("Arial", 17, "bold"))
        delete_button.pack(pady=8, anchor="center")

        # Bind Enter key to save job title
        self.job_title_window.bind("<Return>", lambda event: self.save_job_title())
    
    def refresh_job_title_listbox(self):
        if hasattr(self, 'job_title_listbox'):
            self.job_title_listbox.delete(0, tk.END)
            for title in self.job_titles:
                self.job_title_listbox.insert(tk.END, title)
        self.update_job_title_menus()
    def save_job_title(self):
        job_title = self.entry_job_title.get().strip()
        if job_title:
            try:
                self.db_cursor.execute('''INSERT INTO job_titles (title) VALUES (?)''', (job_title,))
                self.db_connection.commit()
                self.job_titles.append(job_title)
                self.job_titles = sorted(list(set(self.job_titles)))  # Ensure uniqueness and sorting
                self.update_job_title_menus()
                self.refresh_job_title_listbox()
                self.entry_job_title.delete(0, tk.END)
                self.update_filter_options()

                 # Add these lines to refresh the employee list and update the UI
                self.load_job_titles()  # Reload job titles from the database
                self.filter_employees()  # This will call refresh_employee_list
                self.flyer_container.update_idletasks()
            except sqlite3.IntegrityError:
                messagebox.showerror("خطأ", f" الاداره '{job_title}' موجود بالفعل.")
        else:
            messagebox.showerror("خطأ", "يرجى إدخال مسمى وظيفي.")
    def delete_job_title(self):
        selected_indices = self.job_title_listbox.curselection()
        if not selected_indices:
            messagebox.showerror("خطأ", "يرجى اختيار مسمى وظيفي للحذف.")
            return
        
        selected_index = selected_indices[0]
        job_title = self.job_title_listbox.get(selected_index)
        self.db_cursor.execute('''SELECT name FROM employees WHERE job_title = ?''', (job_title,))
        employees_using_title = self.db_cursor.fetchall()
        
        if employees_using_title:
            employee_names = ", ".join([employee[0] for employee in employees_using_title])
            messagebox.showerror("خطأ", f"لا يمكن حذف الاداره  '{job_title}' لأنه مستخدم من قبل الموظفين التاليين: {employee_names}")
        else:
            confirm = messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد أنك تريد حذف الاداره  '{job_title}'؟")
            if confirm:
                self.db_cursor.execute('''DELETE FROM job_titles WHERE title = ?''', (job_title,))
                self.db_connection.commit()
                self.job_titles.remove(job_title)
                self.update_job_title_menus()
                self.refresh_job_title_listbox()
                self.update_filter_options()
                messagebox.showinfo("نجاح", f"تم حذف الاداره  '{job_title}' بنجاح.")
    
    def update_job_title_menus(self):
        # Update job title options in all relevant menus
        for employee in self.employees:
            if 'job_title_menu' in employee and employee['job_title_menu']:
                try:
                    employee['job_title_menu'].configure(values=self.job_titles)
                except tk.TclError:
                    # If the menu no longer exists, remove it from the employee dict
                    employee['job_title_menu'] = None
        
        # Update job title option menus in employee forms if they exist
        if hasattr(self, 'job_title_menu_edit') and self.job_title_menu_edit:
            try:
                self.job_title_menu_edit.configure(values=self.job_titles)
            except tk.TclError:
                # If the menu no longer exists, remove the attribute
                delattr(self, 'job_title_menu_edit')
        
        if hasattr(self, 'job_title_menu') and self.job_title_menu:
            try:
                self.job_title_menu.configure(values=self.job_titles)
            except tk.TclError:
                # If the menu no longer exists, remove the attribute
                delattr(self, 'job_title_menu')
    
    def load_job_titles(self):
        self.db_cursor.execute('''SELECT title FROM job_titles ORDER BY title ASC''')
        rows = self.db_cursor.fetchall()
        self.job_titles = [row[0] for row in rows]
        
        # Initialize filter variables
        if not hasattr(self, 'filter_vars') or self.filter_vars is None:
            self.filter_vars = {}
        for title in self.job_titles:
            if title not in self.filter_vars:
                self.filter_vars[title] = tk.BooleanVar(value=False)
    
    def add_employee(self, event):
        self.new_window = ctk.CTkToplevel(self)
        self.new_window.title("إضافة موظف")
        self.center_window(400, 500, self.new_window)
        self.new_window.grab_set()
        
        label = ctk.CTkLabel(self.new_window, text="أدخل تفاصيل الموظف:", font=("Arial", 17, "bold"), justify="center")
        label.pack(pady=10)
        
        self.entry_name = ctk.CTkEntry(self.new_window, placeholder_text="الاسم", justify='center', font=("Arial", 15))
        self.entry_name.pack(pady=10)
        
        self.entry_id = ctk.CTkEntry(self.new_window, placeholder_text="رقم الهوية", justify='center', font=("Arial", 15))
        self.entry_id.pack(pady=10)
        
        self.entry_phone = ctk.CTkEntry(self.new_window, placeholder_text="رقم الهاتف", justify='center', font=("Arial", 15))
        self.entry_phone.pack(pady=10)
        
        # Change placeholder from "الراتب الأساسي" to "اجمالي الراتب"
        self.entry_total_salary = ctk.CTkEntry(self.new_window, placeholder_text="اجمالي الراتب", justify='center', font=("Arial", 15))
        self.entry_total_salary.pack(pady=10)
        
        self.entry_working_hours = ctk.CTkEntry(self.new_window, placeholder_text="ساعات العمل الشهرية", justify='center', font=("Arial", 15))
        self.entry_working_hours.pack(pady=10)
        
        self.job_title_var = tk.StringVar()
        self.job_title_menu = ctk.CTkOptionMenu(self.new_window, variable=self.job_title_var, values=self.job_titles, font=("Arial", 15))
        self.job_title_menu.pack(pady=10)
        
        self.entry_job = ctk.CTkEntry(self.new_window, placeholder_text="الوظيفه", justify='center', font=("Arial", 15))
        self.entry_job.pack(pady=10)
        
        save_button = ctk.CTkButton(self.new_window, text="حفظ", command=self.save_employee, font=("Arial", 15))
        save_button.pack(pady=10)
        
        self.new_window.after(100, lambda: self.entry_name.focus_set())
        
        # Bind events for deselection and Enter key
        self.new_window.bind("<Button-1>", lambda event: self.deselect_fields(event))
        self.new_window.bind("<Return>", lambda event: self.save_employee())
    
    
    def deselect_fields(self, event):
        if hasattr(self, 'new_window') and event.widget == self.new_window:
            self.new_window.focus_set()
        elif hasattr(self, 'edit_window') and event.widget == self.edit_window:
            self.edit_window.focus_set()
    
    def save_employee(self):
        name = self.entry_name.get()
        id_number = self.entry_id.get()
        phone = self.entry_phone.get()
        total_salary_input = self.entry_total_salary.get()
        job_title = self.job_title_var.get()
        job = self.entry_job.get().strip()
        working_hours = int(self.entry_working_hours.get())

        # Validate numeric fields
        try:
            total_salary = float(total_salary_input)
            if total_salary <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("خطأ", "يرجى إدخال اجمالي راتب صالح أكبر من الصفر.")
            return

        # Compute basic salary
        basic_salary = total_salary * 0.65

        # Check if an employee with the same name already exists
        try:
            self.db_cursor.execute('''SELECT * FROM employees WHERE name = ?''', (name,))
            existing_employee = self.db_cursor.fetchone()
        except sqlite3.Error as e:
            messagebox.showerror("خطأ في قاعدة البيانات", f"حدث خطأ: {e}")
            return

        if existing_employee:
            messagebox.showerror("خطأ", f"يوجد موظف بالاسم '{name}' بالفعل.")
            return

        try:
            self.db_cursor.execute('''INSERT INTO employees (name, id_number, phone, salary, job_title, job, status, full_package, working_hours) 
                                    VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)''',
                                (name, id_number, phone, basic_salary, job_title, job, total_salary, working_hours))
            self.db_connection.commit()
        except sqlite3.Error as e:
            messagebox.showerror("خطأ في قاعدة البيانات", f"حدث خطأ: {e}")
            return

        employee = {
            "id": self.db_cursor.lastrowid,
            "name": name,
            "id_number": id_number,
            "phone": phone,
            "salary": basic_salary,
            "job_title": job_title,
            "job": job,
            "notes": "",
            "status": "active",
            "full_package": total_salary,
            "working_hours": working_hours,
            "performance": 10,
            "dedication": 10,
            "responsibility": 10,
            "job_title_menu": None
        }
        self.employees.append(employee)
        self.filtered_employees.append(employee)
        
        # Clear existing flyers and recreate them
        for widget in self.flyer_container.winfo_children():
            widget.destroy()
        
        # Group employees by job title
        employees_by_title = {}
        for emp in self.filtered_employees:
            title = emp['job_title']
            if title not in employees_by_title:
                employees_by_title[title] = []
            employees_by_title[title].append(emp)
        
        # Create separators and employee flyers for each job title
        for title, emps in employees_by_title.items():
            self.create_job_title_separator(title)
            for emp in emps:
                self.create_employee_flyer(emp)
        
        self.flyer_container.update_idletasks()
        self.new_window.destroy()
    
    def refresh_employee_list(self):
        # Clear all existing content in the flyer container
        for widget in self.flyer_container.winfo_children():
            widget.destroy()
        
        # Group employees by job title
        employees_by_title = {}
        for employee in self.filtered_employees:
            title = employee['job_title']
            if title not in employees_by_title:
                employees_by_title[title] = []
            employees_by_title[title].append(employee)
        
        # Create separators and employee flyers for each job title
        for title, employees in employees_by_title.items():
            if employees:  # Only create separator if there are employees for this title
                self.create_job_title_separator(title)
                for employee in employees:
                    self.create_employee_flyer(employee)
        
        # Update the geometry of the flyer container
        self.flyer_container.update_idletasks()
        self.flyer_container.configure(height=self.flyer_container.winfo_reqheight())
    def create_job_title_separator(self, title):
    
        separator_frame = ctk.CTkFrame(self.flyer_container, height=30, corner_radius=0)
        separator_frame.pack(fill=tk.X, padx=5, pady=(10, 5))
        separator_frame.pack_propagate(False)

        title_label = ctk.CTkLabel(separator_frame, text=title, font=("Arial", 17, "bold"), justify="right")
        title_label.pack(side=tk.RIGHT, padx=10)

        line = ctk.CTkFrame(separator_frame, height=2)
        line.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
    
    def create_employee_flyer(self, employee):
        if (self.active_view and employee["status"] != "active") or (not self.active_view and employee["status"] != "inactive"):
            return  # Do not create flyer if it doesn't match the current view
        
        flyer_frame = ctk.CTkFrame(self.flyer_container, corner_radius=5, fg_color=("gray90", "gray25"), height=40)
        flyer_frame.pack(fill=tk.X, padx=10, pady=2)
        flyer_frame.pack_propagate(False)

        name_label = ctk.CTkLabel(flyer_frame, text=employee["name"], font=("Arial", 19, "bold"), justify="right")
        name_label.pack(side=tk.RIGHT, padx=10)

        def on_enter(e):
            flyer_frame.configure(fg_color=("gray85", "gray30"))
            name_label.configure(text_color=("gray20", "gray90"))

        def on_leave(e):
            flyer_frame.configure(fg_color=("gray90", "gray25"))
            name_label.configure(text_color=("black", "white"))

        def on_click(e):
            self.show_employee_details(employee)

        flyer_frame.bind("<Enter>", on_enter)
        flyer_frame.bind("<Leave>", on_leave)
        flyer_frame.bind("<Button-1>", on_click)
        name_label.bind("<Enter>", on_enter)
        name_label.bind("<Leave>", on_leave)
        name_label.bind("<Button-1>", on_click)

        self.flyer_container.update_idletasks()
        return flyer_frame
    
    def update_salary_frame(self, employee):
        # Get transaction totals from database
        self.db_cursor.execute('''
            SELECT 
                SUM(CASE WHEN transaction_type = 'الاضافي' THEN amount ELSE 0 END) as total_extra,
                SUM(CASE WHEN transaction_type = 'حافز' THEN amount ELSE 0 END) as total_flat_bonus,
                SUM(CASE WHEN transaction_type = 'الخصم' THEN amount ELSE 0 END) as total_deduction,
                SUM(CASE WHEN transaction_type = 'السلف' THEN amount ELSE 0 END) as total_borrowed
            FROM transactions
            WHERE employee_id = ?
        ''', (employee['id'],))

        transaction_data = self.db_cursor.fetchone()

        # Handle case where there are no transactions
        total_bonus = transaction_data[0] or 0
        total_bonus_flat = transaction_data[1] or 0
        total_deduction = transaction_data[2] or 0   
        total_borrowed = transaction_data[3] or 0

        full_package = employee['full_package']
        adjusted_package = full_package + total_bonus_flat + total_bonus - total_deduction - total_borrowed

        # Clear existing widgets in the right_frame
        for widget in self.right_frame.winfo_children():
            widget.destroy()

        # Create a grid layout with 3 columns and 2 rows
        grid_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True, pady=(0, 10), padx=10)

        # Configure grid weights to allow columns to expand equally
        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)
        grid_frame.grid_columnconfigure(2, weight=1)
        grid_frame.grid_rowconfigure(0, weight=1)
        grid_frame.grid_rowconfigure(1, weight=1)

        # Column 1: اجمالي الراتب and اجمالي المستحق
        salary_info_frame = ctk.CTkFrame(grid_frame, fg_color="transparent")
        salary_info_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=5, pady=5)

        # اجمالي الراتب Label
        ctk.CTkLabel(
            salary_info_frame, 
            text=f"اجمالي الراتب: ج.م{full_package:.2f}", 
            font=("Arial", 16, "bold"), 
            text_color="white"
        ).pack(anchor="center", pady=(0, 10))

        # اجمالي المستحق Label
        ctk.CTkLabel(
            salary_info_frame, 
            text=f"اجمالي المستحق: ج.م{adjusted_package:.2f}", 
            font=("Arial", 16, "bold"), 
            text_color="white"
        ).pack(anchor="center")

        # Column 2: الاضافي and الخصم
        transactions_frame_1 = ctk.CTkFrame(grid_frame, fg_color="transparent")
        transactions_frame_1.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        # الاضافي (Bonus) Label
        ctk.CTkLabel(
            transactions_frame_1, 
            text=f"إجمالي الاضافي: ج.م{total_bonus:.2f}", 
            font=("Arial", 14, "bold"), 
            text_color="white"
        ).pack(anchor="w", pady=(0, 10))

        # الخصم (Deduction) Label
        ctk.CTkLabel(
            transactions_frame_1, 
            text=f"إجمالي الخصومات: ج.م{total_deduction:.2f}", 
            font=("Arial", 14, "bold"), 
            text_color="white"
        ).pack(anchor="w")

        # Column 3: حافز and السلف
        transactions_frame_2 = ctk.CTkFrame(grid_frame, fg_color="transparent")
        transactions_frame_2.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)

        # حافز (Flat Bonus) Label
        ctk.CTkLabel(
            transactions_frame_2, 
            text=f"إجمالي الحافز: ج.م{total_bonus_flat:.2f}", 
            font=("Arial", 14, "bold"), 
            text_color="white"
        ).pack(anchor="w", pady=(0, 10))

        # السلف (Borrow) Label
        ctk.CTkLabel(
            transactions_frame_2, 
            text=f"إجمالي السلف: ج.م{total_borrowed:.2f}", 
            font=("Arial", 14, "bold"), 
            text_color="white"
        ).pack(anchor="w")

        # Add Reset Button frame
        lock_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        lock_frame.pack(pady=(20, 10), fill="x", anchor="e", padx=10)

        # Reset All Transactions Button
        self.reset_button = ctk.CTkButton(
            lock_frame,
            text="إعاده التعين",
            command=self.reset_all_transactions,
            fg_color="red",
            font=("Arial", 17, "bold"),
            hover_color="dark red"
        )
        self.reset_button.pack(side="right", padx=(0, 10))

        # Reset Current Employee Transactions Button
        self.single_reset_btn = ctk.CTkButton(
            lock_frame,
            text="↻",  # Circular arrow icon
            command=lambda: self.reset_transactions(employee),
            font=("Arial", 16),
            width=40,
            height=40,
            corner_radius=20,  # Makes it circular
            fg_color="green",
            hover_color="darkgreen"
        )
        self.single_reset_btn.pack(side="right", padx=(0, 5))

    def reset_transactions(self, employee):
        """Delete all transactions for the specified employee after confirmation."""
        confirm = messagebox.askyesno(
            "تأكيد",
            f"هل أنت متأكد أنك تريد حذف جميع المعاملات لـ {employee['name']}؟"
        )
        if confirm:
            try:
                # Delete transactions from the database
                self.db_cursor.execute(
                    'DELETE FROM transactions WHERE employee_id = ?',
                    (employee['id'],)
                )
                self.db_connection.commit()

                # Refresh the salary frame to reflect changes
                self.update_salary_frame(employee)

                messagebox.showinfo("نجاح", "تم حذف جميع المعاملات بنجاح.")
            except sqlite3.Error as e:
                messagebox.showerror("خطأ", f"حدث خطأ أثناء حذف المعاملات: {e}")
    
    def show_employee_details(self, employee):
        metric_mapping = {"الأداء": "performance", "الالتزام": "dedication", "التعامل": "responsibility"}

        # If a details frame exists, destroy it
        if self.details_frame:
            self.details_frame.destroy()

        # Hide placeholder
        self.placeholder.pack_forget()

        # Create new frame but keep it hidden initially
        temp_frame = ctk.CTkFrame(self.inner_content, fg_color="transparent")
        temp_frame.pack(fill="both", expand=True, padx=10, pady=10)
        temp_frame.pack_forget()  # Hide while building

        # Content area with metrics and details
        content_frame = ctk.CTkFrame(temp_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)

        # Header with name and close button
        header_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        close_btn = ctk.CTkButton(header_frame, text="X", command=self.close_employee_details,
                             width=25, height=15, fg_color="red")
        close_btn.pack(side="left")
        
        name_label = ctk.CTkLabel(header_frame, text=f"{employee['name']}", 
                             font=("Arial", 22, "bold"))
        name_label.pack(side="right")

        # Main content with two columns
        main_content = ctk.CTkFrame(content_frame, fg_color="transparent")
        main_content.pack(fill="both", expand=True, padx=10, pady=10)

        # Left column (Metrics)
        metrics_frame = tk.Frame(main_content, borderwidth=2, relief="solid",
                           bg=self._apply_appearance_mode(self._fg_color))
        metrics_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

        metrics_content = ctk.CTkFrame(metrics_frame, fg_color="transparent")
        metrics_content.pack(fill="both", expand=True, padx=10, pady=10)

        self.metric_vars = {}
        for metric in ["الأداء", "الالتزام", "التعامل"]:
            metric_frame = ctk.CTkFrame(metrics_content)
            metric_frame.pack(fill="x", pady=5)
            
            ctk.CTkLabel(metric_frame, text=metric, font=("Arial", 18, "bold")).pack(pady=(5, 15))
            
            score_frame = ctk.CTkFrame(metric_frame, fg_color=("grey80", "grey20"))
            score_frame.pack(pady=(0, 0), padx=2)
            
            button_frame = ctk.CTkFrame(score_frame, fg_color="transparent")
            button_frame.pack(pady=5)
            
            minus_btn = ctk.CTkButton(button_frame, text="-", width=30, height=30,
                                 command=lambda m=metric: self.adjust_score(employee, m, -1))
            minus_btn.grid(row=0, column=0, padx=5)
            
            english_metric = metric_mapping[metric]
            current_value = employee.get(english_metric, 0)
            self.metric_vars[metric] = tk.StringVar(value=f"{current_value}/10")
            
            score_label = ctk.CTkLabel(button_frame, textvariable=self.metric_vars[metric],
                                  font=("Arial", 16, "bold"))
            score_label.grid(row=0, column=1, padx=5)
            
            plus_btn = ctk.CTkButton(button_frame, text="+", width=30, height=30,
                                command=lambda m=metric: self.adjust_score(employee, m, 1))
            plus_btn.grid(row=0, column=2, padx=5)

        # Total grade section
        grade_frame = ctk.CTkFrame(metrics_content)
        grade_frame.pack(fill="x", pady=(5, 2))
        
        ctk.CTkLabel(grade_frame, text="التقييم الإجمالي",
                 font=("Arial", 20, "bold")).pack()
        
        self.total_score_var = tk.StringVar()
        self.grade_var = tk.StringVar()
        
        total_score_label = ctk.CTkLabel(grade_frame, textvariable=self.total_score_var,
                                    font=("Arial", 18, "bold"))
        total_score_label.pack()
        
        self.grade_label = ctk.CTkLabel(grade_frame, textvariable=self.grade_var,
                                   font=("Arial", 18, "bold"))
        self.grade_label.pack()
        
        self.update_grade(employee)

        # Right column (Details)
        details_frame = tk.Frame(main_content, borderwidth=2, relief="solid", bg="#1E90FF")
        details_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))

        details_content = ctk.CTkFrame(details_frame, fg_color="#1E90FF")
        details_content.pack(fill="both", expand=True, padx=10, pady=10)

        # Calculate salary components
        main_salary = employee['full_package']
        transportation = 0.10 * main_salary
        residency = 0.25 * main_salary
        basic_salary = main_salary - (transportation + residency)

        # Employee details
        details = [
            ("الرقم القومي:", employee['id_number']),
            ("الهاتف:", employee['phone']),
            ("اجمالي الراتب:", f"ج.م{main_salary:.2f}"),
            ("بدل الانتقالات:", f"ج.م{transportation:.2f}"),
            ("بدل السكن:", f"ج.م{residency:.2f}"),
            ("الراتب الاساسي :", f"ج.م{basic_salary:.2f}"),
            ("الاداره :", employee['job_title']),
            ("الوظيفه:", employee['job']),
            ("ساعات العمل الشهرية:", employee['working_hours'])
        ]

        for field, value in details:
            row = ctk.CTkFrame(details_content, fg_color="transparent")
            row.pack(fill="x", pady=10)
            
            ctk.CTkLabel(row, text=field, font=("Arial", 18, "bold"),
                     text_color="white").pack(side="right", padx=2)
            ctk.CTkLabel(row, text=str(value), font=("Arial", 18, "bold"),
                     text_color="white").pack(side="left", padx=2)

        # Bottom section (Salary adjustments)
        salary_frame = ctk.CTkFrame(temp_frame, fg_color="gray20", height=250)
        salary_frame.pack(fill="x", padx=10, pady=(10, 5))
        salary_frame.pack_propagate(False)

        # Left side of salary frame
        left_frame = ctk.CTkFrame(salary_frame, fg_color="transparent")
        left_frame.pack(side="left", fill="both", expand=True, padx=10, pady=5)

        # Right side of salary frame
        self.right_frame = ctk.CTkFrame(salary_frame, fg_color="transparent")
        self.right_frame.pack(side="right", fill="both", expand=True, padx=10, pady=5)

        # Transaction inputs
        adjustments_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        adjustments_frame.pack(fill="x", pady=5)

        # Create transaction entry rows
        transaction_types = [
            ("الاضافي (ساعات):", "bonus_var", "الاضافي"),
            ("الخصم (ساعات):", "deduction_var", "الخصم"),
            ("حافز:", "flat_bonus_var", "حافز"),
            ("السلف:", "borrow_var", "السلف")
        ]

        for label_text, var_name, trans_type in transaction_types:
            frame = ctk.CTkFrame(adjustments_frame, fg_color="transparent")
            frame.pack(fill="x", pady=2)
            
            ctk.CTkLabel(frame, text=label_text, font=("Arial", 14, "bold"),
                     text_color="white", width=150).pack(side="left")
            
            setattr(self, var_name, tk.StringVar(value="0"))
            ctk.CTkEntry(frame, textvariable=getattr(self, var_name),
                     width=80).pack(side="left", padx=5)
            
            ctk.CTkButton(frame, text="إضافة",
                      command=lambda t=trans_type: self.add_transaction(employee, t),
                      font=("Arial", 12, "bold")).pack(side="left")

        # Export button
        button_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=5)
        export_button = ctk.CTkButton(button_frame, text="تصدير", 
                  font=("Arial", 18, "bold"), width=120,
                  command=self.show_export_options)
        export_button.pack(side="right", padx=(0, 10))

        # Action buttons at the bottom
        action_frame = ctk.CTkFrame(temp_frame, fg_color="transparent")
        action_frame.pack(fill="x", padx=10, pady=5, side="bottom")
        # Configure grid columns to share space equally
        action_frame.grid_columnconfigure(0, weight=1) # Column for Delete
        action_frame.grid_columnconfigure(1, weight=1) # Column for Edit
        action_frame.grid_columnconfigure(2, weight=1) # Column for Move Active/Inactive

        # Place buttons using grid
        if employee["status"] == "active":
            move_button = ctk.CTkButton(action_frame, text="نقل إلى غير النشط",
                                      command=lambda: self.move_to_inactive(employee),
                                      font=("Arial", 17, "bold"))
            move_button.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        else: # Corrected: Removed duplicate else
            move_button = ctk.CTkButton(action_frame, text="نقل إلى النشط",
                                      command=lambda: self.move_to_active(employee),
                                      font=("Arial", 17, "bold"))
            move_button.grid(row=0, column=2, padx=5, pady=5, sticky="ew")


        edit_button = ctk.CTkButton(action_frame, text="تعديل",
                                  command=lambda: self.edit_employee(employee),
                                  font=("Arial", 17, "bold"))
        edit_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        

        delete_button = ctk.CTkButton(action_frame, text="حذف",
                                    command=lambda: self.delete_employee(employee),
                                    fg_color="red", hover_color="darkred", # Make delete more distinct
                                    font=("Arial", 17, "bold"))
        delete_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew") # Added missing grid call

        # Update salary information
        self.update_salary_frame(employee)

        # Force layout calculation while hidden
        temp_frame.update_idletasks()
        
        # Show the complete frame
        temp_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.details_frame = temp_frame

    def calculate_adjusted_package(self, employee):
        # Compute the adjusted package based on transactions
        self.db_cursor.execute('''
            SELECT 
                SUM(CASE WHEN transaction_type = 'الاضافي' THEN amount ELSE 0 END) as total_extra,
                SUM(CASE WHEN transaction_type = 'حافز' THEN amount ELSE 0 END) as total_flat_bonus,
                SUM(CASE WHEN transaction_type = 'الخصم' THEN amount ELSE 0 END) as total_deduction,
                SUM(CASE WHEN transaction_type = 'السلف' THEN amount ELSE 0 END) as total_borrowed
            FROM transactions
            WHERE employee_id = ?
        ''', (employee['id'],))
        transaction_data = self.db_cursor.fetchone()

        if transaction_data:
            total_extra, total_flat_bonus, total_deduction, total_borrowed = transaction_data
        else:
            total_extra = total_flat_bonus = total_deduction = total_borrowed = 0

        full_package = employee['full_package']
        adjusted_package = full_package + (total_flat_bonus or 0) + (total_extra or 0) - (total_deduction or 0) - (total_borrowed or 0)

        return adjusted_package
    
    def update_scroll_region(self, event=None):
        self.employee_frame.configure(scrollregion=self.employee_frame.bbox("all"))
    

    def update_filter_options(self):
        if hasattr(self, 'filter_menu') and self.filter_menu.winfo_exists():
            self.destroy_filter_menu()
            self.show_filter_menu()
        
    def on_mousewheel(self, event):
        self.employee_frame.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def close_employee_details(self):
        if self.details_frame:
            self.details_frame.destroy()
        self.placeholder.pack(expand=True)
    
    def load_employee_data(self):
        self.db_cursor.execute('''SELECT * FROM employees''')
        columns = [description[0] for description in self.db_cursor.description]
        rows = self.db_cursor.fetchall()
        self.employees = []
        for row in rows:
            employee = {
                "id": row[columns.index("id")],
                "name": row[columns.index("name")],
                "id_number": row[columns.index("id_number")],
                "phone": row[columns.index("phone")],
                "salary": row[columns.index("salary")],
                "job_title": row[columns.index("job_title")],
                "job": row[columns.index("job")],
                "notes": row[columns.index("notes")] if "notes" in columns else "",
                "status": row[columns.index("status")] if "status" in columns else "active",
                "performance": row[columns.index("performance")] if "performance" in columns else 10,
                "dedication": row[columns.index("dedication")] if "dedication" in columns else 10,
                "responsibility": row[columns.index("responsibility")] if "responsibility" in columns else 10,
                "full_package": row[columns.index("full_package")] if "full_package" in columns else 10,
                "working_hours": row[columns.index("working_hours")] if "working_hours" in columns else 270,
                "job_title_menu": None
            }
            self.employees.append(employee)
        self.filter_employees()
        self.refresh_employee_list()
    
    def edit_employee(self, employee):
        self.edit_window = ctk.CTkToplevel(self)
        self.edit_window.title("تعديل الموظف")
        self.center_window(400, 650, self.edit_window)
        self.edit_window.grab_set()
        
        label = ctk.CTkLabel(self.edit_window, text="أدخل تفاصيل الموظف:", font=("Arial", 19, "bold"), justify="right")
        label.pack(pady=(20, 10))
        
        # Name
        name_label = ctk.CTkLabel(self.edit_window, text="الاسم:", font=("Arial", 19, "bold"), justify="right")
        name_label.pack(pady=(7, 0))
        self.entry_name_edit = ctk.CTkEntry(self.edit_window, placeholder_text="الاسم", justify="right")
        self.entry_name_edit.insert(0, employee["name"])
        self.entry_name_edit.pack(pady=(0, 7))
        
        # ID Number
        id_label = ctk.CTkLabel(self.edit_window, text="رقم الهوية:", font=("Arial", 19, "bold"), justify="right")
        id_label.pack(pady=(7, 0))
        self.entry_id_edit = ctk.CTkEntry(self.edit_window, placeholder_text="رقم الهوية", justify="right")
        self.entry_id_edit.insert(0, employee["id_number"])
        self.entry_id_edit.pack(pady=(0, 7))
        
        # Phone Number
        phone_label = ctk.CTkLabel(self.edit_window, text="رقم الهاتف:", font=("Arial", 19, "bold"), justify="right")
        phone_label.pack(pady=(7, 0))
        self.entry_phone_edit = ctk.CTkEntry(self.edit_window, placeholder_text="رقم الهاتف", justify="right")
        self.entry_phone_edit.insert(0, employee["phone"])
        self.entry_phone_edit.pack(pady=(0, 7))
        
        # اجمالي الراتب
        total_salary_label = ctk.CTkLabel(self.edit_window, text="اجمالي الراتب:", font=("Arial", 19, "bold"), justify="right")
        total_salary_label.pack(pady=(7, 0))
        self.entry_total_salary_edit = ctk.CTkEntry(self.edit_window, placeholder_text="اجمالي الراتب", justify="right")
        self.entry_total_salary_edit.insert(0, str(employee["full_package"]))
        self.entry_total_salary_edit.pack(pady=(0, 7))
        
        # Job Title
        job_title_label = ctk.CTkLabel(self.edit_window, text="الاداره :", font=("Arial", 19, "bold"), justify="right")
        job_title_label.pack(pady=(7, 0))
        self.job_title_var_edit = tk.StringVar(value=employee["job_title"])
        self.job_title_menu_edit = ctk.CTkOptionMenu(self.edit_window, variable=self.job_title_var_edit, values=self.job_titles, font=("Arial", 17, "bold"))
        self.job_title_menu_edit.pack(pady=(0, 7))
        
        # Job
        job_label = ctk.CTkLabel(self.edit_window, text="الوظيفه:", font=("Arial", 19, "bold"), justify="right")
        job_label.pack(pady=(7, 0))
        self.entry_job_edit = ctk.CTkEntry(self.edit_window, placeholder_text="الوظيفه", justify="right")
        self.entry_job_edit.insert(0, employee["job"])
        self.entry_job_edit.pack(pady=(0, 7))
        
        # Working Hours
        working_hours_label = ctk.CTkLabel(self.edit_window, text="ساعات العمل الشهرية:", font=("Arial", 19, "bold"), justify="right")
        working_hours_label.pack(pady=(7, 0))
        self.entry_working_hours_edit = ctk.CTkEntry(self.edit_window, placeholder_text="ساعات العمل الشهرية", justify="right")
        self.entry_working_hours_edit.insert(0, str(employee["working_hours"]))
        self.entry_working_hours_edit.pack(pady=(0, 7))
        
        save_button = ctk.CTkButton(self.edit_window, text="حفظ", command=lambda: self.save_edited_employee(employee), font=("Arial", 17, "bold"))
        save_button.pack(pady=20)
        
        # Bind events for deselection and Enter key
        self.edit_window.bind("<Button-1>", lambda event: self.deselect_fields(event))
        self.edit_window.bind("<Return>", lambda event: self.save_edited_employee(employee))
    
    def save_edited_employee(self, employee):
        name = self.entry_name_edit.get()
        id_number = self.entry_id_edit.get()
        phone = self.entry_phone_edit.get()
        total_salary_input = self.entry_total_salary_edit.get()
        job_title = self.job_title_var_edit.get()
        job = self.entry_job_edit.get().strip()
        working_hours = int(self.entry_working_hours_edit.get())

        try:
            total_salary = float(total_salary_input)
            if total_salary <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("خطأ", "يرجى إدخال اجمالي راتب صالح أكبر من الصفر.")
            return

        basic_salary = total_salary * 0.65

        try:
            self.db_cursor.execute('''UPDATE employees 
                                SET name = ?, id_number = ?, phone = ?, salary = ?, 
                                    job_title = ?, job = ?, full_package = ?, working_hours = ? 
                                WHERE id = ?''',
                                (name, id_number, phone, basic_salary, job_title, job, 
                                total_salary, working_hours, employee["id"]))
            self.db_connection.commit()
        except sqlite3.Error as e:
            messagebox.showerror("خطأ في قاعدة البيانات", f"حدث خطأ: {e}")
            return

        # Update employee data
        employee.update({
            "name": name,
            "id_number": id_number,
            "phone": phone,
            "salary": basic_salary,
            "job_title": job_title,
            "job": job,
            "full_package": total_salary,
            "working_hours": working_hours
        })

        self.refresh_employee_list()
        self.flyer_container.update_idletasks()
        self.edit_window.destroy()
    
    def on_search_enter(self, event=None):
        """Handle search when Enter is pressed"""
        self.filter_employees()
    
    def show_filter_menu(self):
        # Check if filter_menu exists and is a valid widget
        if hasattr(self, 'filter_menu') and isinstance(self.filter_menu, tk.Toplevel) and self.filter_menu.winfo_exists():
            self.filter_menu.destroy()
        
        x = self.filter_button.winfo_rootx()
        y = self.filter_button.winfo_rooty() + self.filter_button.winfo_height()

        self.filter_menu = ctk.CTkToplevel(self)
        self.filter_menu.geometry(f"+{x}+{y}")
        self.filter_menu.overrideredirect(True)
        self.filter_menu.configure(fg_color=("gray85", "gray20"))

        # Load the latest job titles
        self.load_job_titles()

        if not hasattr(self, 'filter_vars'):
            self.filter_vars = {}

        for title in self.job_titles:
            if title not in self.filter_vars:
                self.filter_vars[title] = tk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(self.filter_menu, text=title, variable=self.filter_vars[title],
                                       command=self.apply_filter)
            checkbox.pack(padx=10, pady=5, anchor='e')

        reset_button = ctk.CTkButton(self.filter_menu, text="إعادة تعيين", command=self.reset_filter)
        reset_button.pack(pady=10)

        self.filter_menu.bind("<FocusOut>", lambda e: self.destroy_filter_menu())
        self.filter_menu.focus_set()

        # Ensure the filter button can be clicked again
        self.filter_button.configure(state="normal")

        # Lift the menu to the top
        self.filter_menu.lift()
        self.filter_menu.attributes('-topmost', True)
        self.filter_menu.after_idle(self.filter_menu.attributes, '-topmost', False)


    def destroy_filter_menu(self):
        if hasattr(self, 'filter_menu') and self.filter_menu.winfo_exists():
            self.filter_menu.destroy()
            self.filter_menu = None

    def apply_filter(self):
        self.filter_employees()

    def reset_filter(self):
        for var in self.filter_vars.values():
            var.set(False)
        self.filter_employees()

    def filter_employees(self):
        # Remove extra spaces and convert search term to a single string without spaces
        search_term = self.search_var.get().strip().lower()
        search_term_no_spaces = search_term.replace(" ", "")
        
        selected_titles = [title for title, var in self.filter_vars.items() if var.get()]
        
        status_filter = 'active' if self.active_view else 'inactive'
        
        self.filtered_employees = [
            employee for employee in self.employees
            if (
                search_term in employee['name'].lower() or
                search_term_no_spaces in employee['name'].lower().replace(" ", "") or  # Add this line
                search_term in employee['id_number'].lower() or
                search_term in employee['job_title'].lower()
            ) and (
                not selected_titles or employee['job_title'] in selected_titles
            ) and (
                employee['status'] == status_filter
            )
        ]
        
        self.refresh_employee_list()

    def delete_employee(self, employee):
        confirm = messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد أنك تريد حذف {employee['name']}؟")
        if confirm:
            try:
                self.db_connection.execute('BEGIN')
                
                # Delete associated transactions first
                self.db_cursor.execute('''DELETE FROM transactions WHERE employee_id = ?''', 
                                    (employee["id"],))
                
                # Then delete the employee
                self.db_cursor.execute('''DELETE FROM employees WHERE id = ?''', 
                                    (employee["id"],))
                
                self.db_connection.commit()
                
                # Remove from lists
                self.employees = [e for e in self.employees if e["id"] != employee["id"]]
                self.filtered_employees = [e for e in self.filtered_employees if e["id"] != employee["id"]]
                
                self.close_employee_details()
                self.refresh_employee_list()
                
                messagebox.showinfo("نجاح", f"تم حذف {employee['name']} وجميع المعاملات المرتبطة به.")
            
            except sqlite3.Error as e:
                self.db_connection.rollback()
                messagebox.showerror("خطأ", f"حدث خطأ أثناء حذف الموظف: {e}")
    
    def show_active_employees(self):
        self.active_view = True
        self.active_button.configure(fg_color="#007acc", hover_color="#005f99")  # Highlight active button
        self.inactive_button.configure(fg_color="red", hover_color="darkred")
        self.filter_employees()
    
    def show_inactive_employees(self):
        self.active_view = False
        self.active_button.configure(fg_color="#007acc", hover_color="#005f99")
        self.inactive_button.configure(fg_color="darkred", hover_color="red")  # Highlight inactive button
        self.filter_employees()
    
    def move_to_inactive(self, employee):
        confirm = messagebox.askyesno("تأكيد", f"هل أنت متأكد أنك تريد نقل {employee['name']} إلى غير نشط؟")
        if confirm:
            try:
                self.db_cursor.execute('''UPDATE employees SET status = ? WHERE id = ?''', 
                                    ('inactive', employee["id"]))
                self.db_connection.commit()
                
                # Verify the update
                self.db_cursor.execute('''SELECT status FROM employees WHERE id = ?''', 
                                    (employee["id"],))
                result = self.db_cursor.fetchone()
                
                if result and result[0] == 'inactive':
                    employee['status'] = 'inactive'
                    self.close_employee_details()
                    self.filter_employees()
                else:
                    raise Exception("Failed to update employee status")
                    
            except Exception as e:
                self.db_connection.rollback()
                messagebox.showerror("خطأ", f"فشل تحديث حالة الموظف: {str(e)}")
    
    def move_to_active(self, employee):
        confirm = messagebox.askyesno("تأكيد", f"هل أنت متأكد أنك تريد نقل {employee['name']} إلى نشط؟")
        if confirm:
            try:
                self.db_cursor.execute('''UPDATE employees SET status = ? WHERE id = ?''', 
                                    ('active', employee["id"]))
                self.db_connection.commit()
                
                # Verify the update
                self.db_cursor.execute('''SELECT status FROM employees WHERE id = ?''', 
                                    (employee["id"],))
                result = self.db_cursor.fetchone()
                
                if result and result[0] == 'active':
                    employee['status'] = 'active'
                    self.close_employee_details()
                    self.filter_employees()
                else:
                    raise Exception("Failed to update employee status")
                    
            except Exception as e:
                self.db_connection.rollback()
                messagebox.showerror("خطأ", f"فشل تحديث حالة الموظف: {str(e)}")

    # Adjust the grade and total score
    def update_grade(self, employee):
        performance = employee.get("performance", 10)
        dedication = employee.get("dedication", 10)
        responsibility = employee.get("responsibility", 10)
        total_score = performance + dedication + responsibility
        
        self.total_score_var.set(f"{total_score}/30")
        
        if total_score >= 27:
            grade = "ممتاز"
            color = "green"
        elif total_score >= 21:
            grade = "جيد"
            color = "blue"
        elif total_score >= 15:
            grade = "مقبول"
            color = "yellow"
        else:
            grade = "سيئ"
            color = "red"
        
        self.grade_var.set(grade)
        self.grade_label.configure(text_color=color)

    def adjust_score(self, employee, metric, change):
        english_metric = {"الأداء": "performance", "الالتزام": "dedication", "التعامل": "responsibility"}[metric]
        new_score = employee.get(english_metric, 0) + change
        new_score = max(0, min(new_score, 10))  # Ensure score stays between 0 and 10
        employee[english_metric] = new_score
        self.db_cursor.execute(f'''UPDATE employees SET {english_metric} = ? WHERE id = ?''', (new_score, employee["id"]))
        self.db_connection.commit()
        self.metric_vars[metric].set(f"{new_score}/10")
        self.update_grade(employee)
    
    # Save notes function
    def save_notes(self, employee):
        notes = self.notes_text.get("1.0", tk.END).strip()
        try:
            self.db_cursor.execute('''UPDATE employees SET notes = ? WHERE id = ?''', 
                                (notes, employee["id"]))
            self.db_connection.commit()
            employee["notes"] = notes
            messagebox.showinfo("نجاح", "تم حفظ الملاحظات بنجاح")
        except sqlite3.Error as e:
            messagebox.showerror("خطأ", f"فشل حفظ الملاحظات: {e}")
    
    
    
    def export_to_excel(self):
        try:
            # Get all active employees with their transactions
            self.db_cursor.execute('''
                SELECT e.id, e.name, e.job, e.full_package,
                       SUM(CASE WHEN t.transaction_type = 'الاضافي' THEN t.amount ELSE 0 END) as extra,
                       SUM(CASE WHEN t.transaction_type = 'الخصم' THEN t.amount ELSE 0 END) as deduction,
                       SUM(CASE WHEN t.transaction_type = 'حافز' THEN t.amount ELSE 0 END) as bonus,
                       SUM(CASE WHEN t.transaction_type = 'السلف' THEN t.amount ELSE 0 END) as loan,
                       e.job_title
                FROM employees e
                LEFT JOIN transactions t ON e.id = t.employee_id
                WHERE e.status = 'active'
                GROUP BY e.id
                ORDER BY e.job_title, e.name
            ''')
            employees_data = self.db_cursor.fetchall()

            # Create DataFrame
            df = pd.DataFrame(employees_data, columns=[
                'ID', 'الاسم', 'الوظيفة', 'اجمالي الراتب',
                'الاضافي', 'الخصم', 'حافز', 'سلف', 'القسم'
            ])

            # Group employees by department
            department_groups = df.groupby('القسم')

            # Create Excel writer
            current_date = datetime.now().strftime("%Y-%m-%d")
            default_filename = f"تقرير_الموظفين_{current_date}.xlsx"

            filename = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx")],
                initialfile=default_filename
            )

            if not filename:
                return

            # Create a new workbook
            workbook = openpyxl.Workbook()
            worksheet = workbook.active
            worksheet.title = 'تقرير الموظفين'

            # Set RTL
            worksheet.sheet_view.rightToLeft = True

            # Define styles
            header_font = openpyxl.styles.Font(bold=True, size=11)
            normal_font = openpyxl.styles.Font(size=11)
            dept_font = openpyxl.styles.Font(bold=True, size=11)
            total_font = openpyxl.styles.Font(bold=True, size=11, color="FF0000")  # Red color for totals
            
            thin_border = openpyxl.styles.Border(
                left=openpyxl.styles.Side(style='thin'),
                right=openpyxl.styles.Side(style='thin'),
                top=openpyxl.styles.Side(style='thin'),
                bottom=openpyxl.styles.Side(style='thin')
            )

            # Write headers in the exact order from the image
            headers = ['الاسم', 'الوظيفة', 'الاضافي', 'الخصم', 'حافز', 'سلف', 'اجمالي الراتب', 'الصافي']
            for col, header in enumerate(headers, 1):
                cell = worksheet.cell(row=1, column=col)
                cell.value = header
                cell.font = header_font
                cell.border = thin_border
                cell.alignment = openpyxl.styles.Alignment(horizontal='center')

            current_row = 2
            grand_total = 0

            # Write data for each department
            for dept_name, dept_data in department_groups:
                # Write department name
                cell = worksheet.cell(row=current_row, column=1)
                cell.value = dept_name
                cell.font = dept_font
                cell.alignment = openpyxl.styles.Alignment(horizontal='center')
                worksheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=len(headers))
                for col in range(1, len(headers) + 1):
                    worksheet.cell(row=current_row, column=col).border = thin_border
                current_row += 1

                dept_total = 0
                # Write employee data
                for _, emp in dept_data.iterrows():
                    # Calculate الصافي (net amount) using اجمالي المستحق formula
                    net_amount = emp['اجمالي الراتب'] + emp['الاضافي'] + emp['حافز'] - emp['الخصم'] - emp['سلف']
                    dept_total += net_amount
                    row_data = [
                        emp['الاسم'],  # الاسم
                        emp['الوظيفة'],  # الوظيفة
                        emp['الاضافي'],  # الاضافي
                        emp['الخصم'],  # الخصم
                        emp['حافز'],  # حافز
                        emp['سلف'],  # سلف
                        emp['اجمالي الراتب'],  # اجمالي الراتب
                        net_amount,  # الصافي (اجمالي المستحق)
                    ]
                    for col, value in enumerate(row_data, 1):
                        cell = worksheet.cell(row=current_row, column=col)
                        cell.value = value
                        cell.border = thin_border
                        cell.font = normal_font
                        # Right align text for name and job title, center for numbers
                        if col in [1, 2]:  # الاسم and الوظيفة columns
                            cell.alignment = openpyxl.styles.Alignment(horizontal='right')
                        else:
                            cell.alignment = openpyxl.styles.Alignment(horizontal='center')
                            if isinstance(value, (int, float)):
                                cell.number_format = '#,##0.00'
                    current_row += 1

                # Write department total
                total_row = ["الاجمالي", "", "", "", "", "", "", dept_total]
                gray_fill = openpyxl.styles.PatternFill(start_color='D3D3D3', end_color='D3D3D3', fill_type='solid')
                for col, value in enumerate(total_row, 1):
                    cell = worksheet.cell(row=current_row, column=col)
                    cell.value = value
                    cell.border = thin_border
                    cell.fill = gray_fill
                    cell.font = total_font if col == 8 else dept_font
                    cell.alignment = openpyxl.styles.Alignment(horizontal='center')
                    if col == 8:  # Total amount
                        cell.number_format = '#,##0.00'
                current_row += 1
                grand_total += dept_total

            # Write grand total
            current_row += 1
            total_row = ["الاجمالي الكلي", "", "", "", "", "", "", grand_total]
            for col, value in enumerate(total_row, 1):
                cell = worksheet.cell(row=current_row, column=col)
                cell.value = value
                cell.border = thin_border
                cell.fill = gray_fill
                cell.font = total_font if col == 1 else dept_font
                cell.alignment = openpyxl.styles.Alignment(horizontal='center')
                if col == 1:  # Total amount
                    cell.number_format = '#,##0.00'

            # Adjust column widths
            for column in worksheet.columns:
                max_length = 0
                column = [cell for cell in column]
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[openpyxl.utils.get_column_letter(column[0].column)].width = adjusted_width

            # Save the workbook
            workbook.save(filename)
            messagebox.showinfo("تم التصدير بنجاح", f"تم تصدير البيانات إلى {filename}")
            return True

        except Exception as e:
            messagebox.showerror("فشل التصدير", f"حدث خطأ أثناء التصدير: {str(e)}")
            return False
    
    def add_transaction(self, employee, transaction_type):
        try:
            if transaction_type in ["الاضافي", "الخصم"]:
                # Fixed attribute access from 'extra_var' to 'bonus_var' for 'الاضافي'
                field_var = "bonus_var" if transaction_type == "الاضافي" else "deduction_var"
                value = float(getattr(self, field_var).get())
                if value < 0:
                    raise ValueError
                # Calculate amount based on hours
                hourly_rate = employee['full_package'] / employee['working_hours']
                amount = value * hourly_rate
            elif transaction_type == "حافز":
                amount = float(self.flat_bonus_var.get())
                if amount < 0:
                    raise ValueError
            elif transaction_type == "السلف":
                amount = float(self.borrow_var.get())
                if amount < 0:
                    raise ValueError
            else:
                raise ValueError("Invalid transaction type")

            if amount > 0:
                self.db_cursor.execute('''
                    INSERT INTO transactions (employee_id, transaction_type, amount)
                    VALUES (?, ?, ?)
                ''', (employee['id'], transaction_type, amount))
                self.db_connection.commit()

                # Reset input field
                if transaction_type == "الاضافي":
                    self.bonus_var.set("0")
                elif transaction_type == "الخصم":
                    self.deduction_var.set("0")
                elif transaction_type == "حافز":
                    self.flat_bonus_var.set("0")
                elif transaction_type == "السلف":
                    self.borrow_var.set("0")

                # Update the salary frame
                self.update_salary_frame(employee)
            
            else:
                messagebox.showerror("خطأ", "يجب أن يكون المبلغ أكبر من الصفر.")
        
        except ValueError:
            messagebox.showerror("خطأ", "يرجى إدخال رقم صالح وغير سالب.")
    
    
    def reset_all_transactions(self):
        export_confirm = messagebox.askyesno("تصدير البيانات", "هل ترغب في تصدير البيانات قبل إعادة التعيين؟")
        # First, trigger export
        if export_confirm:
            export_success = self.export_to_excel(triggered_by_reset=True)
            if not export_success:
                messagebox.showerror("فشل التصدير", "لم يتم تصدير البيانات. تم إلغاء إعادة التعيين.")
                return

        confirm = messagebox.askyesno("تأكيد الحذف", "هل أنت متأكد أنك تريد إعادة تعيين جميع المعاملات لجميع الموظفين؟")
        if confirm:
            try:
                self.db_cursor.execute('DELETE FROM transactions')
                self.db_connection.commit()
                messagebox.showinfo("نجاح", "تم إعادة تعيين جميع المعاملات بنجاح.")

                # Update the salary frame for all employees
                for employee in self.employees:
                    self.update_salary_frame(employee)

            except sqlite3.Error as e:
                messagebox.showerror("خطأ", f"حدث خطأ أثناء إعادة تعيين المعاملات: {e}")

    def show_export_options(self):
        """Show export options dropdown menu"""
        # Create a dropdown menu
        export_menu = tk.Menu(self, tearoff=0)
        export_menu.add_command(label="تصدير إلى Excel", command=self.export_to_excel)
        export_menu.add_command(label="تصدير كشوف المرتبات (PDF)", command=self.show_pdf_export_options)
        
        # Get the position of the export button
        button_x = self.winfo_pointerx()  # Get the current mouse x position
        button_y = self.winfo_pointery()  # Get the current mouse y position
        
        # Show the menu at the mouse position
        export_menu.post(button_x, button_y)
        
        # Bind a click event to destroy the menu when clicked elsewhere
        self.bind("<Button-1>", lambda event: export_menu.unpost())

    def show_pdf_export_options(self):
        """Show PDF export scope options"""
        # Create a dropdown menu for PDF export options
        pdf_menu = tk.Menu(self, tearoff=0)
        
        # If an employee is currently selected, enable the "Current Employee" option
        if hasattr(self, 'current_employee') and self.current_employee:
            pdf_menu.add_command(label="تصدير الموظف الحالي فقط", 
                                command=lambda: self.export_to_pdf(single_employee=True))
        else:
            pdf_menu.add_command(label="تصدير الموظف الحالي فقط", state="disabled")
        
        # Always enable the "All Employees" option
        pdf_menu.add_command(label="تصدير جميع الموظفين", 
                            command=lambda: self.export_to_pdf(single_employee=False))
        
        # Get the current mouse position for the submenu
        button_x = self.winfo_pointerx()
        button_y = self.winfo_pointery()
        
        # Show the menu at the mouse position
        pdf_menu.post(button_x, button_y)
        
        # Bind a click event to destroy the menu when clicked elsewhere
        self.bind("<Button-1>", lambda event: pdf_menu.unpost())

    def export_to_pdf(self, single_employee=False):
        """Export salary slips to PDF"""
        try:
            # Import the PDF generation module
            from salary_slip_pdf import generate_salary_slips, get_employee_transactions
            
            # Get current date for filename
            current_date = datetime.now().strftime("%Y%m%d")
            default_filename = f"كشوف_المرتبات_{current_date}.pdf"
            
            # Ask user for save location
            filename = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")],
                initialfile=default_filename
            )
            
            if not filename:
                return
                
            # Determine which employees to include
            if single_employee:
                # Export only the current employee
                employee_ids = [self.current_employee['id']]
            else:
                # Get all active employees
                self.db_cursor.execute('SELECT id FROM employees WHERE status = "active" ORDER BY name')
                employee_ids = [row[0] for row in self.db_cursor.fetchall()]
                
            # Show progress dialog for multiple employees
            if len(employee_ids) > 2 and not single_employee:
                progress_window = ctk.CTkToplevel(self)
                progress_window.title("جاري التصدير...")
                progress_window.geometry("300x100")
                progress_window.resizable(False, False)
                
                # Center the progress window
                self.center_window(300, 100, progress_window)
                
                # Add progress label
                progress_label = ctk.CTkLabel(progress_window, text="جاري إنشاء كشوف المرتبات...", font=("Arial", 14))
                progress_label.pack(pady=10)
                
                # Add progress bar
                progress_bar = ctk.CTkProgressBar(progress_window)
                progress_bar.pack(pady=10, padx=20, fill="x")
                
                # Start progress animation
                progress_bar.start()
                
                # Update the UI
                progress_window.update()
                
                # Generate the PDF
                output_file = generate_salary_slips(employee_ids, filename)
                
                # Close progress window
                progress_window.destroy()
            else:
                # Generate the PDF without progress bar for small number of employees
                output_file = generate_salary_slips(employee_ids, filename)
            
            # Show success message
            messagebox.showinfo("تم التصدير بنجاح", f"تم تصدير كشوف المرتبات إلى {filename}")
            
        except Exception as e:
            messagebox.showerror("فشل التصدير", f"حدث خطأ أثناء التصدير: {str(e)}")
            logging.error(f"PDF export error: {str(e)}")



if __name__ == "__main__":
    app = EmployeeManager()
    app.mainloop()