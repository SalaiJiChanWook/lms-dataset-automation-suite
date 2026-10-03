import ctypes
import os
import sys
import time
import zipfile
import threading
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from dotenv import load_dotenv

# Selenium Components
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Google Drive API (Service Account)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# Load environment configurations
load_dotenv()

# Taskbar Process ID for Windows
try:
    APP_ID = "org.automation.lms.datacollector.v2"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
except Exception:
    pass

# System Configurations
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_KEY_PATH", "service_account.json")
DEFAULT_LMS_URL = os.getenv("LMS_PORTAL_URL", "http://192.168.0.101")
LMS_USER = os.getenv("LMS_ADMIN_USER", "")
LMS_PASS = os.getenv("LMS_ADMIN_PASS", "")


def resource_path(relative_path: str) -> str:
    """PyInstaller bundle temp path သို့မဟုတ် လက်ရှိ directory ကို ရှာဖွေပေးခြင်း"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class BECAApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="superhero")
        self.title("LMS Academic Data Extraction & Cloud Synchronization Suite")
        self.geometry("1020x760")
        self.minsize(940, 680)

        icon_path = resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # State Variables
        self.site_url = tk.StringVar(value=DEFAULT_LMS_URL)
        self.download_dir = tk.StringVar(value=os.path.abspath(os.getcwd()))
        self.zip_name = tk.StringVar()
        self.drive_folder_id = tk.StringVar(value=os.getenv("DRIVE_DEFAULT_FOLDER_ID", ""))
        self.selected_programs = set()
        self.driver = None

        self.collect_btn = None
        self.send_btn = None
        self._prog_vars = {}

        self._build_ui()

    def _build_ui(self):
        top_banner = ttk.Frame(self, padding=(16, 10))
        top_banner.pack(fill=X)
        ttk.Label(
            top_banner, 
            text="LMS Automation & Cloud Sync Console", 
            font=("Segoe UI", 14, "bold"),
            bootstyle="light"
        ).pack(side=LEFT)
        self.status_tag = ttk.Label(
            top_banner, 
            text="System Ready", 
            font=("Segoe UI", 9, "bold"),
            bootstyle="success-inverse", 
            padding=(8, 2)
        )
        self.status_tag.pack(side=RIGHT)

        self.notebook = ttk.Notebook(self, bootstyle="primary")
        self.notebook.pack(fill=BOTH, expand=True, padx=16, pady=(0, 8))

        self.tab_collection = ttk.Frame(self.notebook, padding=12)
        self.tab_sending = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.tab_collection, text=" 📥 Data Collection ")
        self.notebook.add(self.tab_sending, text=" 📤 Database Sync & Upload ")

        self._build_tab_collection()
        self._build_tab_sending()
        self._build_log_console()

    def _build_tab_collection(self):
        env_card = ttk.Labelframe(self.tab_collection, text=" Environment & Target Settings ", padding=12)
        env_card.pack(fill=X, pady=(0, 10))
        env_card.columnconfigure(1, weight=1)

        ttk.Label(env_card, text="Target LMS Portal:").grid(row=0, column=0, sticky=W, pady=6, padx=(0, 10))
        ttk.Entry(env_card, textvariable=self.site_url).grid(row=0, column=1, sticky=EW, pady=6)

        ttk.Label(env_card, text="Output Directory:").grid(row=1, column=0, sticky=W, pady=6, padx=(0, 10))
        path_box = ttk.Frame(env_card)
        path_box.grid(row=1, column=1, sticky=EW, pady=6)
        path_box.columnconfigure(0, weight=1)

        ttk.Entry(path_box, textvariable=self.download_dir).grid(row=0, column=0, sticky=EW)
        ttk.Button(path_box, text="Browse...", bootstyle="info-outline", width=10, command=self._browse_download_dir).grid(row=0, column=1, padx=(8, 0))

        subj_card = ttk.Labelframe(self.tab_collection, text=" Subject Extraction Targets ", padding=12)
        subj_card.pack(fill=BOTH, expand=True, pady=(0, 10))

        ctrl_bar = ttk.Frame(subj_card)
        ctrl_bar.pack(fill=X, pady=(0, 8))
        ttk.Label(ctrl_bar, text="Select subjects to collect data:", font=("Segoe UI", 9, "bold")).pack(side=LEFT)
        ttk.Button(ctrl_bar, text="Select All", bootstyle="link", command=self._select_all_programs).pack(side=RIGHT, padx=4)
        ttk.Button(ctrl_bar, text="Clear All", bootstyle="link", command=self._clear_all_programs).pack(side=RIGHT, padx=4)

        programs = [
            "Myanmar", "English", "Math", "Chemistry", 
            "Physics", "Economics", "Biology", "History", 
            "Geography", "SocialScience", "OptionalMyanmar"
        ]

        grid_frame = ttk.Frame(subj_card)
        grid_frame.pack(fill=BOTH, expand=True)
        for c in range(4):
            grid_frame.columnconfigure(c, weight=1)

        for i, p in enumerate(programs):
            v = tk.IntVar(value=1)
            cb = ttk.Checkbutton(grid_frame, text=p, variable=v, bootstyle="info-round-toggle")
            cb.grid(row=i // 4, column=i % 4, sticky=W, padx=10, pady=8)
            self._prog_vars[p] = v

        action_card = ttk.Frame(self.tab_collection)
        action_card.pack(fill=X, pady=4)

        self.collect_btn = ttk.Button(
            action_card, 
            text="▶ Start Data Collection Process", 
            bootstyle=SUCCESS, 
            padding=(16, 8),
            command=self._on_start_collection
        )
        self.collect_btn.pack(side=LEFT, padx=(0, 8))

        ttk.Button(
            action_card, 
            text="Open Manual Chrome", 
            bootstyle="secondary-outline", 
            padding=(12, 8),
            command=self._open_chrome_manual
        ).pack(side=LEFT, padx=4)

        ttk.Button(
            action_card, 
            text="Clear Console", 
            bootstyle="dark-outline", 
            padding=(12, 8),
            command=self._clear_log
        ).pack(side=RIGHT)

    def _build_tab_sending(self):
        auth_card = ttk.Labelframe(self.tab_sending, text=" Cloud Credentials Status ", padding=14)
        auth_card.pack(fill=X, pady=(0, 10))
        auth_card.columnconfigure(1, weight=1)

        ttk.Label(auth_card, text="Authentication Mode:").grid(row=0, column=0, sticky=W, pady=6, padx=(0, 10))
        file_box = ttk.Frame(auth_card)
        file_box.grid(row=0, column=1, sticky=EW, pady=6)
        file_box.columnconfigure(0, weight=1)

        status_text = "Service Account Key Found" if os.path.exists(SERVICE_ACCOUNT_FILE) else "Key File Pending"
        status_color = "success" if os.path.exists(SERVICE_ACCOUNT_FILE) else "warning"
        self.creds_label = ttk.Label(file_box, text=status_text, bootstyle=status_color)
        self.creds_label.grid(row=0, column=0, sticky=W)

        meta_card = ttk.Labelframe(self.tab_sending, text=" Remote Sync Parameters ", padding=14)
        meta_card.pack(fill=X, pady=(0, 10))
        meta_card.columnconfigure(1, weight=1)

        ttk.Label(meta_card, text="Target Folder ID:").grid(row=0, column=0, sticky=W, pady=8, padx=(0, 10))
        ttk.Entry(meta_card, textvariable=self.drive_folder_id).grid(row=0, column=1, sticky=EW, pady=8)
        ttk.Label(meta_card, text="(Optional: leave blank for root)").grid(row=0, column=2, sticky=W, padx=(8, 0))

        ttk.Label(meta_card, text="Archive File Name:").grid(row=1, column=0, sticky=W, pady=8, padx=(0, 10))
        ttk.Entry(meta_card, textvariable=self.zip_name).grid(row=1, column=1, sticky=EW, pady=8)
        ttk.Label(meta_card, text="(Optional: auto-generated if blank)").grid(row=1, column=2, sticky=W, padx=(8, 0))

        send_actions = ttk.Frame(self.tab_sending)
        send_actions.pack(fill=X, pady=8)

        self.send_btn = ttk.Button(
            send_actions, 
            text="🚀 Compress & Send to Drive", 
            bootstyle=SUCCESS, 
            padding=(16, 8),
            command=self._on_send_to_drive
        )
        self.send_btn.pack(side=LEFT, padx=(0, 8))

        ttk.Button(
            send_actions, 
            text="Verify Credentials", 
            bootstyle="info-outline", 
            padding=(12, 8),
            command=self._test_credentials
        ).pack(side=LEFT, padx=4)

        ttk.Button(
            send_actions, 
            text="Clean Local Files", 
            bootstyle="danger-outline", 
            padding=(12, 8),
            command=lambda: self._purge_local_files(interactive=True)
        ).pack(side=LEFT, padx=4)

        ttk.Button(
            send_actions, 
            text="Switch to Collection", 
            bootstyle="secondary-outline", 
            padding=(12, 8),
            command=lambda: self.notebook.select(self.tab_collection)
        ).pack(side=RIGHT)

    def _build_log_console(self):
        log_frame = ttk.Labelframe(self, text=" Execution Output & Activity Log ", padding=(10, 6))
        log_frame.pack(fill=BOTH, expand=False, padx=16, pady=(0, 12))

        self.log = scrolledtext.ScrolledText(
            log_frame, 
            height=9, 
            wrap=tk.WORD, 
            font=("Consolas", 9), 
            bg="#1b232c", 
            fg="#e0e6ed"
        )
        self.log.pack(fill=BOTH, expand=True)

    # ---------------- UI Helpers ----------------
    def log_message(self, msg: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log.insert(tk.END, f"[{ts}] {msg}\n")
        self.log.see(tk.END)
        print(f"[{ts}] {msg}")

    def _clear_log(self):
        self.log.delete("1.0", tk.END)

    def _select_all_programs(self):
        for var in self._prog_vars.values():
            var.set(1)

    def _clear_all_programs(self):
        for var in self._prog_vars.values():
            var.set(0)

    def _browse_download_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.download_dir.set(d)
            self.log_message(f"Download path configured: {d}")

    def _purge_local_files(self, interactive=True):
        ddir = self.download_dir.get()
        if not os.path.isdir(ddir):
            messagebox.showerror("Path Error", "Target directory does not exist.")
            return

        if interactive:
            confirm = messagebox.askyesno(
                "Confirm Clean Up",
                f"Are you sure you want to permanently delete all .ods, .csv, and .zip files in:\n{ddir}?"
            )
            if not confirm:
                return

        deleted_count = 0
        try:
            for root, _, files in os.walk(ddir):
                for f in files:
                    if f.lower().endswith((".ods", ".csv", ".zip")):
                        file_path = os.path.join(root, f)
                        try:
                            os.remove(file_path)
                            deleted_count += 1
                        except Exception as err:
                            self.log_message(f"Failed to delete {f}: {err}")

            self.log_message(f"File cleanup complete: {deleted_count} local file(s) removed.")
            if interactive:
                messagebox.showinfo("Clean Up Finished", f"Successfully deleted {deleted_count} local file(s).")
        except Exception as e:
            self.log_message(f"Clean up operation error: {e}")
            if interactive:
                messagebox.showerror("Error", str(e))

    # ---------------- Automation Core ----------------
    def _create_chrome_driver(self, download_dir, detach=False):
        options = Options()
        prefs = {
            "download.default_directory": os.path.abspath(download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "safebrowsing.disable_download_protection": True
        }
        options.add_experimental_option("prefs", prefs)
        if detach:
            options.add_experimental_option("detach", True)
        options.add_argument("--no-sandbox")
        options.add_argument("--start-maximized")
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

    def _open_chrome_manual(self):
        try:
            ddir = self.download_dir.get() or os.getcwd()
            driver = self._create_chrome_driver(download_dir=ddir, detach=True)
            url = self.site_url.get().strip()
            driver.get(url)
            self.log_message("Manual browser instance launched successfully.")
        except Exception as e:             
            self.log_message(f"Browser launch failed: {e}")
            messagebox.showerror("Error", str(e))

    def _on_start_collection(self):
        self.selected_programs = {k for k, v in self._prog_vars.items() if v.get() == 1}
        if not self.selected_programs:
            messagebox.showwarning("Warning", "Please select at least one subject to extract.")
            return

        if not self.site_url.get().strip():
            messagebox.showerror("Configuration Error", "Please provide a valid LMS portal URL.")
            return

        if not os.path.isdir(self.download_dir.get()):
            if messagebox.askyesno("Create Directory", f"Directory {self.download_dir.get()} does not exist. Create now?"):
                os.makedirs(self.download_dir.get(), exist_ok=True)
            else:
                return

        self.status_tag.config(text="Extracting Data...", bootstyle="warning-inverse")
        self.collect_btn.config(state="disabled")
        threading.Thread(target=self._run_collection_thread, daemon=True).start()

    def _run_collection_thread(self):
        try:
            self.log_message("=== Initializing Data Collection Sequence ===")
            ddir = self.download_dir.get()
            self.driver = self._create_chrome_driver(download_dir=ddir, detach=False)
            url = self.site_url.get().strip()
            self.log_message(f"Connecting to portal: {url}")
            self.driver.get(url)            

            downloader = SeleniumDownloader(self.driver, self.log_message)
            
            # Login authentication
            if LMS_USER and LMS_PASS:
                self.log_message("Authenticating LMS session...")
                downloader.login(LMS_USER, LMS_PASS)
            else:
                self.log_message("No login credentials found in environment; proceeding as guest/existing session.")

            downloader.run_for_programs(self.selected_programs)

            self.log_message("Finalizing stream flush and disk writes...")
            time.sleep(4)
            self.log_message("=== Data extraction sequence finished successfully ===")
            messagebox.showinfo("Success", "Data extraction finished. Output saved to download folder.")
        except Exception as e:
            self.log_message(f"Extraction error: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            try:
                if self.driver:
                    self.driver.quit()
                    self.log_message("Automation driver stopped cleanly.")
            except Exception:
                pass
            self.collect_btn.config(state="normal")
            self.status_tag.config(text="System Ready", bootstyle="success-inverse")

    # ---------------- Service Account & Cloud Sync ----------------
    def _test_credentials(self):
        try:
            creds = self._get_credentials()
            if creds:
                messagebox.showinfo("Authentication", "Service Account credentials validated successfully.")
                self.log_message("Service Account verification successful.")
            else:
                self.log_message("Authorization failed: invalid credentials state.")
                messagebox.showerror("Authentication", "Unable to obtain valid service account credentials.")
        except Exception as e:
            self.log_message(f"Credentials verification error: {e}")
            messagebox.showerror("Error", str(e))

    def _on_send_to_drive(self):
        if not os.path.isdir(self.download_dir.get()):
            messagebox.showerror("Path Error", "Configured download directory does not exist.")
            return

        self.status_tag.config(text="Uploading Files...", bootstyle="info-inverse")
        self.send_btn.config(state="disabled")
        threading.Thread(target=self._run_send_thread, daemon=True).start()

    def _run_send_thread(self):
        try:
            ddir = self.download_dir.get()
            all_files = []
            for root, _, files in os.walk(ddir):
                for f in files:
                    if f.lower().endswith((".ods", ".csv")):
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, ddir)
                        all_files.append((full, rel))

            if not all_files:
                self.log_message("No .ods or .csv dataset files detected.")
                messagebox.showwarning("Notice", "No .ods or .csv datasets available in target directory.")
                return

            zipname = self.zip_name.get().strip() or f"academic_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            if not zipname.lower().endswith(".zip"):
                zipname += ".zip"
            zip_path = os.path.join(ddir, zipname)

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for full, rel in all_files:
                    zf.write(full, arcname=rel)
            self.log_message(f"Created compressed package: {zip_path}")

            self.log_message("Authenticating Google Drive API service...")
            creds = self._get_credentials()
            service = build('drive', 'v3', credentials=creds)
            media = MediaFileUpload(zip_path, mimetype="application/zip")
            metadata = {"name": os.path.basename(zip_path)}
            folder_id = self.drive_folder_id.get().strip()
            if folder_id:
                metadata["parents"] = [folder_id]

            self.log_message(f"Transferring payload {os.path.basename(zip_path)} to Google Drive...")
            uploaded = service.files().create(body=metadata, media_body=media, fields="id").execute()
            file_id = uploaded.get("id")
            self.log_message(f"Transmission complete. File Reference ID: {file_id}")
            messagebox.showinfo("Success", f"Archive uploaded successfully.\nFile ID: {file_id}")

            if messagebox.askyesno("Local Cleanup", "Upload completed successfully. Would you like to clean up local datasets and zip files now?"):
                self._purge_local_files(interactive=False)

        except Exception as e:
            self.log_message(f"Transmission failure: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            self.send_btn.config(state="normal")
            self.status_tag.config(text="System Ready", bootstyle="success-inverse")

    def _get_credentials(self):
        target_path = resource_path(SERVICE_ACCOUNT_FILE)
        if os.path.exists(target_path):
            return service_account.Credentials.from_service_account_file(
                target_path, 
                scopes=SCOPES
            )
        raise FileNotFoundError(f"Service Account key file '{SERVICE_ACCOUNT_FILE}' not found.")


# ---------------- Extraction Automation Engine (DRY Architecture) ----------------
class SeleniumDownloader:
    def __init__(self, driver: webdriver.Chrome, logger):
        self.driver = driver
        self.log = logger
        self.wait = WebDriverWait(self.driver, 10)

    def _safe_click(self, xpath: str, delay: float = 1.0) -> bool:
        try:
            element = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            element.click()
            time.sleep(delay)
            return True
        except Exception:
            try:
                # Fallback to direct elements finding
                els = self.driver.find_elements(By.XPATH, xpath)
                if els:
                    els[0].click()
                    time.sleep(delay)
                    return True
            except Exception as e:
                self.log(f"Action failed at xpath {xpath}: {e}")
        return False

    def scroll_page(self, pages: int = 1, direction: str = "down"):
        key = Keys.PAGE_DOWN if direction == "down" else Keys.PAGE_UP
        try:
            body = self.driver.find_elements(By.TAG_NAME, "body")
            if body:
                for _ in range(pages):
                    body[0].send_keys(key)
                    time.sleep(0.5)
        except Exception as e:
            self.log(f"Page scroll error: {e}")

    def login(self, username, password):
        try:
            inputs = self.wait.until(EC.presence_of_all_elements_located((By.XPATH, "//form//input")))
            if len(inputs) >= 2:
                inputs[0].send_keys(username)
                inputs[1].send_keys(password)
                btn = self.driver.find_element(By.XPATH, "//form//button[@type='submit']")
                btn.click()
                time.sleep(2)
        except Exception as e:
            self.log(f"Login sequence error: {e}")

    def download_grade_export(self):
        self.log("Downloading Grade Export...")
        self._safe_click("/html/body/div[2]/div[4]/div/header/div/div[1]/div[1]/nav/ol/li[1]/a")
        self._safe_click("/html/body/div[2]/div[4]/div/div[2]/nav/ul/li[4]/a")
        self._safe_click("/html/body/div[2]/div[4]/div/div[3]/div/div/div/div[1]/div/div[1]/nav/div/div")
        self.scroll_page(1, "down")
        self._safe_click("/html/body/div[2]/div[4]/div/div[3]/div/div/div/div[1]/div/div[1]/nav/div/ul/li[3]/ul/li[5]")
        self.scroll_page(2, "down")
        self._safe_click("/html/body/div[2]/div[4]/div/div[3]/div/div/div/form/div[3]/div/div/div/div[2]/input")
        self.scroll_page(1, "up")

    def download_generic_subject(self, name: str, card_index: int, item_index: int = 2, scroll_pre: int = 1):
        """Clean Parameterized Subject Downloader replacing repetitive methods"""
        self.log(f"Downloading {name} dataset...")
        if scroll_pre > 0:
            self.scroll_page(scroll_pre, "down")
        
        self._safe_click("/html/body/div[2]/nav/div/div[1]/nav/ul/li[1]/a", delay=0.8)
        self.scroll_page(1, "down")
        self._safe_click(f"/html/body/div[2]/div[4]/div/div[3]/div/div/div/div/div/div[{card_index}]/div[1]/h3/a")
        self.scroll_page(2, "down")
        self._safe_click(f"/html/body/div[2]/div[4]/div/div[3]/div/div/div/div/div/ul/li/div/div[2]/ul/li[{item_index}]/div/div[2]/div[2]/div/div/a")
        self._safe_click("/html/body/div[2]/div[4]/div/div[2]/nav/ul/li[4]/a")
        self.scroll_page(2, "down")
        self._safe_click("/html/body/div[2]/div[4]/div/div[3]/div/div/div[3]/form[2]/div/button")
        self.scroll_page(3, "up")
        
        try:
            self.download_grade_export()
        except Exception:
            pass
        self.scroll_page(2, "up")
        self.log(f"{name} download finished.")

    def run_for_programs(self, selected_programs):
        # Configuration mapping: (card_index, subitem_index, scroll_pre)
        subject_configs = {
            "Myanmar": (1, 2, 0),
            "English": (2, 2, 1),
            "Math": (3, 2, 1),
            "Chemistry": (4, 2, 1),
            "Physics": (5, 2, 1),
            "Biology": (6, 3, 0),
            "Geography": (7, 2, 0),
            "History": (8, 2, 0),
            "Economics": (9, 2, 0),
            "SocialScience": (10, 2, 0),
            "OptionalMyanmar": (11, 3, 0),
        }

        for p in selected_programs:
            if p in subject_configs:
                try:
                    self.log(f"Processing pipeline: {p}")
                    c_idx, i_idx, s_pre = subject_configs[p]
                    self.download_generic_subject(p, card_index=c_idx, item_index=i_idx, scroll_pre=s_pre)
                    time.sleep(1.0)
                except Exception as e:
                    self.log(f"Extraction error on {p}: {e}")


if __name__ == "__main__":
    app = BECAApp()
    app.mainloop()