import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageDraw, ImageFont
import serial
import serial.tools.list_ports
import threading
import time
from tkinter import scrolledtext
import calculations  # Nasz moduł obliczeniowy
import validation    # Nasz moduł walidacji

class GeodeticApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Kalkulator Geodezyjny")
        self.geometry("1000x600") # Nieco większe okno na start
        self.minsize(900, 550)
        # self.resizable(False, False) # Warto odblokować zmianę rozmiaru dla wygody
        
        # Zmienne do przechowywania wyników obliczeń
        self.c_cc = 0.0
        self.mc_cc = 0.0
        self.i_cc = 0.0
        self.mi_cc = 0.0

        # --- Zmienne dla Terminala Serial
        self.serial_port_var = tk.StringVar()
        self.serial_baud_var = tk.IntVar(value=57600)
        self.serial_databits_var = tk.IntVar(value=8)
        self.serial_stopbits_var = tk.DoubleVar(value=1)
        self.serial_parity_var = tk.StringVar(value="None")
        self.serial_flow_var = tk.StringVar(value="None")
        
        self.serial_conn = None
        self.serial_is_connected = False
        self.serial_read_thread = None

        # Listy na odczyty
        self.collimation_readings = []
        self.inclination_readings = []

        # --- Konfiguracja walidacji ---
        self.vcmd = (self.register(validation.validate_number_input), '%P')

        # --- Dolny panel (Stopka) ---
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(side="bottom", fill="x", pady=10, padx=10) 

        author_label = ttk.Label(bottom_frame, text="Autor: Adam Szczęśniak", relief="sunken", padding=2)
        author_label.pack(side="left")

        version_label = ttk.Label(bottom_frame, text="Wersja: 1.0", relief="sunken", padding=2)
        version_label.pack(side="right")
        
        close_button = ttk.Button(bottom_frame, text="Zamknij", command=self.destroy)
        close_button.pack() 

        # --- GŁÓWNY KONTENER Z SUWAKIEM (PanedWindow) ---
        # To naprawi problem z szerokością Menedżera Odczytów
        self.main_pane = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        self.main_pane.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        
        # --- Lewa kolumna: Zakładki obliczeń ---
        self.left_frame = ttk.Frame(self.main_pane)
        self.main_pane.add(self.left_frame, minsize=500) # Dodajemy do panelu
        
        self.notebook = ttk.Notebook(self.left_frame)
        
        self.tab1 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab1, text="Kolimacja")
        self._create_collimation_tab()

        self.tab2 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab2, text="Inklinacja")
        self._create_inclination_tab()
        
        self.tab3 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab3, text="Współczynnik Ng0")
        self._create_refraction_tab()

        self.tab4 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab4, text="Poprawka Atm. (ręczne)")
        self._create_atmos_tab()

        self.batch_data = [] # Przechowalnia wyników do eksportu
        self.tab5 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab5, text="Poprawka Atm. (z pliku)")
        self._create_batch_tab()
        
        self.tab6 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab6, text="Geometria Ziemi")
        self._create_geometry_tab()

        self.tab7 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab7, text="Gen. Topcon")
        self._create_topcon_tab()

        self.tab8 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab8, text="PySerial Terminal")
        self._create_serial_terminal_tab()

        self.notebook.pack(expand=True, fill="both")
        
       # --- Prawa kolumna: Menedżer Odczytów ---
        self.right_frame = ttk.Frame(self.main_pane)
        self.main_pane.add(self.right_frame, minsize=250) # Dodajemy do panelu
        
        self._create_readings_manager(self.right_frame)
        
        # --- Powiązanie zdarzeń ---
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        # Wywołujemy raz ręcznie
        self._on_tab_changed()

    # --- Zakładka 1: Kolimacja ---
    def _create_collimation_tab(self):
        frame = self.tab1
        
        io_frame = ttk.Frame(frame)
        io_frame.pack(fill="x", pady=5)
        
        load_btn = ttk.Button(io_frame, text="Wczytaj dane z pliku", command=self._load_collimation_data)
        load_btn.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5)

        calc_btn = ttk.Button(io_frame, text="Oblicz Kolimację", command=self._calculate_collimation)
        calc_btn.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        ttk.Label(io_frame, text="Średnia kolimacja (cc):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.coll_mean_var = tk.StringVar(value="--")
        ttk.Label(io_frame, textvariable=self.coll_mean_var, font=("TkDefaultFont", 10, "bold")).grid(row=2, column=1, sticky="e", padx=5)
        
        ttk.Label(io_frame, text="Błąd kolimacji (cc):").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.coll_error_var = tk.StringVar(value="--")
        ttk.Label(io_frame, textvariable=self.coll_error_var, font=("TkDefaultFont", 10, "bold")).grid(row=3, column=1, sticky="e", padx=5)
        
        io_frame.columnconfigure(1, weight=1)

        corr_frame = ttk.LabelFrame(frame, text="Poprawiony odczyt", padding=10)
        corr_frame.pack(fill="x", pady=10)

        ttk.Label(corr_frame, text="Odczyt koła poz. H' (g):").grid(row=0, column=0, sticky="w", padx=5)
        self.coll_h_entry = ttk.Entry(corr_frame, validate="key", validatecommand=self.vcmd)
        self.coll_h_entry.grid(row=0, column=1, sticky="e", padx=5, pady=2)
        
        ttk.Label(corr_frame, text="Odczyt koła pion. z' (g):").grid(row=1, column=0, sticky="w", padx=5)
        self.coll_z_entry = ttk.Entry(corr_frame, validate="key", validatecommand=self.vcmd)
        self.coll_z_entry.grid(row=1, column=1, sticky="e", padx=5, pady=2)

        calc_corr_btn = ttk.Button(corr_frame, text="Oblicz poprawkę", command=self._calculate_corrected_collimation)
        calc_corr_btn.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        ttk.Label(corr_frame, text="Poprawiony odczyt H (g):").grid(row=3, column=0, sticky="w", padx=5)
        self.coll_corrected_var = tk.StringVar(value="--")
        ttk.Label(corr_frame, textvariable=self.coll_corrected_var, font=("TkDefaultFont", 10, "bold")).grid(row=3, column=1, sticky="e", padx=5)
        
        corr_frame.columnconfigure(1, weight=1)

    # --- Zakładka 2: Inklinacja ---
    def _create_inclination_tab(self):
        frame = self.tab2
        
        io_frame = ttk.LabelFrame(frame, text="Dane wejściowe", padding=10)
        io_frame.pack(fill="x", pady=5)
        
        load_btn = ttk.Button(io_frame, text="Wczytaj dane z pliku", command=self._load_inclination_data)
        load_btn.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        ttk.Label(io_frame, text="Kolimacja c (cc):").grid(row=2, column=0, sticky="w", padx=5)
        self.incl_c_entry = ttk.Entry(io_frame, validate="key", validatecommand=self.vcmd)
        self.incl_c_entry.grid(row=2, column=1, sticky="e", padx=5, pady=2)
        
        ttk.Label(io_frame, text="Błąd kolimacji mc (cc):").grid(row=3, column=0, sticky="w", padx=5)
        self.incl_mc_entry = ttk.Entry(io_frame, validate="key", validatecommand=self.vcmd)
        self.incl_mc_entry.grid(row=3, column=1, sticky="e", padx=5, pady=2)
        
        ttk.Label(io_frame, text="Kąt zenitalny z (g):").grid(row=4, column=0, sticky="w", padx=5)
        self.incl_z_entry = ttk.Entry(io_frame, validate="key", validatecommand=self.vcmd)
        self.incl_z_entry.grid(row=4, column=1, sticky="e", padx=5, pady=2)

        calc_incl_btn = ttk.Button(io_frame, text="Oblicz Inklinację", command=self._calculate_inclination)
        calc_incl_btn.grid(row=5, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        ttk.Label(io_frame, text="Średnia inklinacja (cc):").grid(row=6, column=0, sticky="w", padx=5)
        self.incl_mean_var = tk.StringVar(value="--")
        ttk.Label(io_frame, textvariable=self.incl_mean_var, font=("TkDefaultFont", 10, "bold")).grid(row=6, column=1, sticky="e", padx=5)
        
        ttk.Label(io_frame, text="Błąd inklinacji (cc):").grid(row=7, column=0, sticky="w", padx=5)
        self.incl_error_var = tk.StringVar(value="--")
        ttk.Label(io_frame, textvariable=self.incl_error_var, font=("TkDefaultFont", 10, "bold")).grid(row=7, column=1, sticky="e", padx=5)
        
        io_frame.columnconfigure(1, weight=1)
        
        corr_frame = ttk.LabelFrame(frame, text="Poprawiony odczyt", padding=10)
        corr_frame.pack(fill="x", pady=10)

        ttk.Label(corr_frame, text="Odczyt koła poz. H' (g):").grid(row=0, column=0, sticky="w", padx=5)
        self.incl_h_entry = ttk.Entry(corr_frame, validate="key", validatecommand=self.vcmd)
        self.incl_h_entry.grid(row=0, column=1, sticky="e", padx=5, pady=2)
        
        ttk.Label(corr_frame, text="Odczyt koła pion. z' (g):").grid(row=1, column=0, sticky="w", padx=5)
        self.incl_z_corr_entry = ttk.Entry(corr_frame, validate="key", validatecommand=self.vcmd)
        self.incl_z_corr_entry.grid(row=1, column=1, sticky="e", padx=5, pady=2)

        calc_corr_btn = ttk.Button(corr_frame, text="Oblicz poprawkę", command=self._calculate_corrected_inclination)
        calc_corr_btn.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        ttk.Label(corr_frame, text="Poprawiony odczyt H (g):").grid(row=3, column=0, sticky="w", padx=5)
        self.incl_corrected_var = tk.StringVar(value="--")
        ttk.Label(corr_frame, textvariable=self.incl_corrected_var, font=("TkDefaultFont", 10, "bold")).grid(row=3, column=1, sticky="e", padx=5)
        
        corr_frame.columnconfigure(1, weight=1)

    # --- Prawa kolumna: Menedżer Odczytów ---
    def _create_readings_manager(self, parent_frame):
        manager_frame = ttk.LabelFrame(parent_frame, text="Menedżer Odczytów", padding=10)
        manager_frame.pack(expand=True, fill="both")
        
        entry_frame = ttk.Frame(manager_frame)
        entry_frame.pack(fill="x", pady=5)
        
        ttk.Label(entry_frame, text="Odczyt I (g):").grid(row=0, column=0, padx=5)
        self.h1_entry = ttk.Entry(entry_frame, width=15, validate="key", validatecommand=self.vcmd)
        self.h1_entry.grid(row=0, column=1, padx=5)
        
        ttk.Label(entry_frame, text="Odczyt II (g):").grid(row=0, column=2, padx=5)
        self.h2_entry = ttk.Entry(entry_frame, width=15, validate="key", validatecommand=self.vcmd)
        self.h2_entry.grid(row=0, column=3, padx=5)
        
        entry_frame.columnconfigure(1, weight=1)
        entry_frame.columnconfigure(3, weight=1)
        
        add_btn = ttk.Button(entry_frame, text="Dodaj odczyt", command=self._add_manual_reading)
        add_btn.grid(row=1, column=0, columnspan=4, sticky="ew", padx=5, pady=5)
        
        display_frame = ttk.Frame(manager_frame)
        display_frame.pack(expand=True, fill="both", pady=5)
        
        ttk.Label(display_frame, text="Odczyt I", font=("TkDefaultFont", 9, "bold")).grid(row=0, column=0, sticky="w", padx=5)
        ttk.Label(display_frame, text="Odczyt II", font=("TkDefaultFont", 9, "bold")).grid(row=0, column=1, sticky="w", padx=10)
        
        text_frame = ttk.Frame(display_frame)
        text_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical")
        self.readings_display = tk.Text(text_frame, height=20, width=40,
                                        state="disabled",
                                        yscrollcommand=scrollbar.set,
                                        font=("Courier New", 9))
        scrollbar.config(command=self.readings_display.yview)
        
        scrollbar.pack(side="right", fill="y")
        self.readings_display.pack(side="left", expand=True, fill="both")

        display_frame.rowconfigure(1, weight=1)
        display_frame.columnconfigure(0, weight=1)
        display_frame.columnconfigure(1, weight=1)
        
        clear_btn = ttk.Button(manager_frame, text="Wyczyść listę", command=self._clear_readings)
        clear_btn.pack(fill="x", padx=5, pady=5)

    # --- Logika Menedżera Odczytów ---
    
    def _on_tab_changed(self, event=None):
        try:
            current_tab_index = self.notebook.index(self.notebook.select())
        except tk.TclError:
            current_tab_index = 0

        # Logika ukrywania/pokazywania w PanedWindow
        if current_tab_index in [0, 1]:
            # Jeśli panelu nie ma na liście (sprawdzamy po stringu), dodajemy go
            if str(self.right_frame) not in self.main_pane.panes():
                self.main_pane.add(self.right_frame, minsize=250)
            self._update_readings_display()
        else:
            # Dla zakładki 3 (i innych) ukrywamy prawy panel bezwarunkowo.
            # Używamy try-except, aby uniknąć błędu, jeśli panel już jest ukryty.
            try:
                self.main_pane.forget(self.right_frame)
            except tk.TclError:
                pass

    def _get_active_readings_list(self):
        try:
            current_tab = self.notebook.index(self.notebook.select())
            if current_tab == 0:
                return self.collimation_readings
            else:
                return self.inclination_readings
        except Exception:
            return self.collimation_readings

    def _update_readings_display(self):
        readings_list = self._get_active_readings_list()
        
        self.readings_display.config(state="normal")
        self.readings_display.delete("1.0", tk.END)
        
        if not readings_list:
            self.readings_display.insert(tk.END, " (Brak odczytów)\n")
        else:
            for h1, h2 in readings_list:
                self.readings_display.insert(tk.END, f"{h1:<15.4f} \t {h2:<15.4f}\n")
                
        self.readings_display.config(state="disabled")
        
    def _add_manual_reading(self):
        try:
            h1 = float(self.h1_entry.get())
            h2 = float(self.h2_entry.get())
        except ValueError:
            messagebox.showerror("Błąd danych", "Wprowadź poprawne liczby Odczyt I oraz Odczyt II.")
            return
            
        readings_list = self._get_active_readings_list()
        readings_list.append((h1, h2))
        
        self._update_readings_display()
        
        self.h1_entry.delete(0, tk.END)
        self.h2_entry.delete(0, tk.END)
        self.h1_entry.focus()
        
    def _clear_readings(self):
        if not messagebox.askyesno("Potwierdzenie", "Czy na pewno chcesz wyczyścić wszystkie odczyty dla tej zakładki?"):
            return
            
        readings_list = self._get_active_readings_list()
        readings_list.clear()
        self._update_readings_display()

    # --- Logika Obliczeniowa ---

    def _load_collimation_data(self):
        file_path = filedialog.askopenfilename(
            title="Wybierz plik z odczytami kolimacji",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")]
        )
        if not file_path:
            return
        
        try:
            new_readings = calculations.parse_collimation_file(file_path)
            self.collimation_readings.extend(new_readings)
            self._update_readings_display()
            messagebox.showinfo("Sukces", f"Dodano {len(new_readings)} odczytów. Kliknij 'Oblicz Kolimację', aby przetworzyć.")
        except Exception as e:
            messagebox.showerror("Błąd pliku", str(e))

    def _calculate_collimation(self):
        if not self.collimation_readings:
            messagebox.showwarning("Brak danych", "Brak odczytów na liście. Wczytaj plik lub dodaj je ręcznie.")
            return

        self.c_cc, self.mc_cc = calculations.calculate_mean_collimation(self.collimation_readings)
        self.coll_mean_var.set(f"{self.c_cc:.2f}")
        self.coll_error_var.set(f"{self.mc_cc:.2f}")

    def _calculate_corrected_collimation(self):
        try:
            h_g = float(self.coll_h_entry.get())
            z_g = float(self.coll_z_entry.get())
        except ValueError:
            messagebox.showerror("Błąd danych", "Wprowadź poprawne wartości H' i z'.")
            return
        
        if self.c_cc is None:
             messagebox.showerror("Brak obliczeń", "Najpierw oblicz kolimację.")
             return

        corrected_h = calculations.calculate_corrected_reading(h_g, z_g, self.c_cc, 0.0)
        self.coll_corrected_var.set(f"{corrected_h:.8f}")

    def _load_inclination_data(self):
        file_path = filedialog.askopenfilename(
            title="Wybierz plik z danymi inklinacji",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")]
        )
        if not file_path:
            return
            
        try:
            data = calculations.parse_inclination_file(file_path)
            self.inclination_readings.extend(data['readings'])
            
            self.incl_c_entry.delete(0, tk.END)
            self.incl_c_entry.insert(0, str(data['c']))
            self.incl_mc_entry.delete(0, tk.END)
            self.incl_mc_entry.insert(0, str(data['mc']))
            self.incl_z_entry.delete(0, tk.END)
            self.incl_z_entry.insert(0, str(data['z']))

            self._update_readings_display()
            messagebox.showinfo("Sukces", f"Wczytano dane i dodano {len(data['readings'])} odczytów. Kliknij 'Oblicz Inklinację'.")
            
        except Exception as e:
            messagebox.showerror("Błąd pliku", str(e))

    def _calculate_inclination(self):
        if not self.inclination_readings:
            messagebox.showerror("Brak danych", "Brak odczytów na liście. Wczytaj plik lub dodaj je ręcznie.")
            return
            
        try:
            c_cc = float(self.incl_c_entry.get())
            mc_cc = float(self.incl_mc_entry.get())
            z_g = float(self.incl_z_entry.get())
        except ValueError:
            messagebox.showerror("Błąd danych", "Wprowadź poprawne wartości c, mc oraz z.")
            return
            
        self.i_cc, self.mi_cc = calculations.calculate_mean_inclination(
            self.inclination_readings, c_cc, mc_cc, z_g
        )
        
        self.incl_mean_var.set(f"{self.i_cc:.2f}")
        self.incl_error_var.set(f"{self.mi_cc:.2f}")

    def _calculate_corrected_inclination(self):
        try:
            h_g = float(self.incl_h_entry.get())
            z_g = float(self.incl_z_corr_entry.get())
            c_cc = float(self.incl_c_entry.get()) 
        except ValueError:
            messagebox.showerror("Błąd danych", "Wprowadź poprawne wartości H', z' oraz c.")
            return

        corrected_h = calculations.calculate_corrected_reading(h_g, z_g, c_cc, self.i_cc)
        self.incl_corrected_var.set(f"{corrected_h:.8f}")

    # --- Zakładka 3: Refrakcja (Ng0) ---
    def _create_refraction_tab(self):
        frame = self.tab3
        
        # Panel sterowania (góra)
        control_frame = ttk.LabelFrame(frame, text="Parametry", padding=10)
        control_frame.pack(fill="x", pady=5)
        
        # Edycja zakresu Lambda
        ttk.Label(control_frame, text="Lambda start [nm]:").pack(side="left", padx=5)
        self.lam_start_entry = ttk.Entry(control_frame, width=8, validate="key", validatecommand=self.vcmd)
        self.lam_start_entry.insert(0, "400")
        self.lam_start_entry.pack(side="left", padx=5)

        ttk.Label(control_frame, text="Lambda koniec [nm]:").pack(side="left", padx=5)
        self.lam_end_entry = ttk.Entry(control_frame, width=8, validate="key", validatecommand=self.vcmd)
        self.lam_end_entry.insert(0, "1600")
        self.lam_end_entry.pack(side="left", padx=5)
        
        ttk.Button(control_frame, text="Generuj Wykres i Tabelę", command=self._generate_refraction_data).pack(side="left", padx=20)

        # Kontener na treść
        content_frame = ttk.Frame(frame)
        content_frame.pack(fill="both", expand=True, pady=5)
        
        # 1. Tabela (Treeview)
        table_frame = ttk.Frame(content_frame, width=250)
        table_frame.pack(side="right", fill="y", padx=5)
        
        columns = ("lambda", "ng0")
        self.ng0_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=15)
        self.ng0_tree.heading("lambda", text="Lambda [nm]")
        self.ng0_tree.heading("ng0", text="Ng0")
        self.ng0_tree.column("lambda", width=80, anchor="center")
        self.ng0_tree.column("ng0", width=80, anchor="center")
        
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.ng0_tree.yview)
        self.ng0_tree.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        self.ng0_tree.pack(side="left", fill="both", expand=True)

        # 2. Wykres (Matplotlib)
        plot_frame = ttk.Frame(content_frame)
        plot_frame.pack(side="left", fill="both", expand=True)
        
        # Zmniejszamy domyślny rozmiar figsize, aby tight_layout miał pole manewru
        self.fig = Figure(figsize=(4, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        
        # Puste ustawienia początkowe
        self.ax.set_title("Współczynnik grupy Ng0")
        self.ax.set_xlabel(r"Długość fali $\lambda$ [nm]") # Użycie 'r' naprawia warning
        self.ax.set_ylabel(r"$N_{g0}$")
        self.ax.grid(True)
        self.fig.tight_layout() # Naprawa ucinania napisów na starcie
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

    def _generate_refraction_data(self):
        # Pobieranie danych z pól edycyjnych
        try:
            start = int(float(self.lam_start_entry.get()))
            end = int(float(self.lam_end_entry.get()))
        except ValueError:
            messagebox.showerror("Błąd", "Wprowadź poprawne liczby dla zakresu lambda.")
            return

        if start >= end:
             messagebox.showerror("Błąd", "Wartość początkowa musi być mniejsza od końcowej.")
             return

        step = 10 
        
        # Obliczenia
        data = calculations.calculate_ng0_curve(start, end, step)
        
        # Aktualizacja tabeli
        for row in self.ng0_tree.get_children():
            self.ng0_tree.delete(row)
            
        x_vals = []
        y_vals = []
        
        for lam, ng0 in data:
            self.ng0_tree.insert("", tk.END, values=(int(lam), f"{ng0:.2f}"))
            x_vals.append(lam)
            y_vals.append(ng0)
            
        # Aktualizacja wykresu
        self.ax.clear()
        self.ax.plot(x_vals, y_vals, marker='o', markersize=3, linestyle='-', color='b')
        self.ax.set_title("Współczynnik grupy Ng0 (Barrell & Sears)")
        
        # Użycie r"..." (raw string) naprawia SyntaxWarning
        self.ax.set_xlabel(r"Długość fali $\lambda$ [nm]") 
        self.ax.set_ylabel(r"$N_{g0}$")
        
        self.ax.grid(True, linestyle='--', alpha=0.7)
        
        # KLUCZOWE: Automatyczne dopasowanie marginesów, aby nie ucinało napisów
        self.fig.tight_layout()
        
        # Odświeżenie płótna
        self.canvas.draw()

    # --- Zakładka 4: Poprawki Atmosferyczne (Manual) ---
    def _create_atmos_tab(self):
        frame = self.tab4
        
        # --- Lewa strona: Dane wejściowe ---
        input_frame = ttk.LabelFrame(frame, text="Parametry pomiaru", padding=15)
        input_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        # Konfiguracja siatki
        input_frame.columnconfigure(1, weight=1)

        # Pola
        ttk.Label(input_frame, text="Długość fali λ [nm]:").grid(row=0, column=0, sticky="w", pady=5)
        self.atm_lam_entry = ttk.Entry(input_frame, validate="key", validatecommand=self.vcmd)
        self.atm_lam_entry.insert(0, "850") # Domyślna dla wielu dalmierzy
        self.atm_lam_entry.grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(input_frame, text="Temp. sucha Ts [°C]:").grid(row=1, column=0, sticky="w", pady=5)
        self.atm_ts_entry = ttk.Entry(input_frame, validate="key", validatecommand=self.vcmd)
        self.atm_ts_entry.grid(row=1, column=1, sticky="ew", padx=5)

        ttk.Label(input_frame, text="Temp. mokra Tm [°C]:").grid(row=2, column=0, sticky="w", pady=5)
        self.atm_tm_entry = ttk.Entry(input_frame, validate="key", validatecommand=self.vcmd)
        self.atm_tm_entry.grid(row=2, column=1, sticky="ew", padx=5)

        ttk.Label(input_frame, text="Ciśnienie P [hPa]:").grid(row=3, column=0, sticky="w", pady=5)
        self.atm_p_entry = ttk.Entry(input_frame, validate="key", validatecommand=self.vcmd)
        self.atm_p_entry.insert(0, "1013.25")
        self.atm_p_entry.grid(row=3, column=1, sticky="ew", padx=5)

        ttk.Label(input_frame, text="Odległość Dzm [m]:").grid(row=4, column=0, sticky="w", pady=5)
        self.atm_d_entry = ttk.Entry(input_frame, validate="key", validatecommand=self.vcmd)
        self.atm_d_entry.grid(row=4, column=1, sticky="ew", padx=5)

        calc_btn = ttk.Button(input_frame, text="Oblicz Poprawki", command=self._calculate_atmos_manual)
        calc_btn.grid(row=5, column=0, columnspan=2, sticky="ew", pady=20)

        # --- Prawa strona: Wyniki ---
        result_frame = ttk.LabelFrame(frame, text="Wyniki obliczeń", padding=15)
        result_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        # Zmienne
        self.res_ng0 = tk.StringVar(value="--")
        self.res_e = tk.StringVar(value="--")
        self.res_ngr = tk.StringVar(value="--")
        self.res_ppm = tk.StringVar(value="--")
        self.res_dd = tk.StringVar(value="--")
        self.res_final = tk.StringVar(value="--")

        # Wyświetlanie
        # Parametry pośrednie
        ttk.Label(result_frame, text="Współczynnik Ng0:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(result_frame, textvariable=self.res_ng0, font=("TkDefaultFont", 9)).grid(row=0, column=1, sticky="e")
        
        ttk.Label(result_frame, text="Ciśnienie pary 'e' [hPa]:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Label(result_frame, textvariable=self.res_e, font=("TkDefaultFont", 9)).grid(row=1, column=1, sticky="e")
        
        ttk.Label(result_frame, text="Współczynnik rzecz. Ngr:").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Label(result_frame, textvariable=self.res_ngr, font=("TkDefaultFont", 9)).grid(row=2, column=1, sticky="e")

        ttk.Separator(result_frame, orient='horizontal').grid(row=3, column=0, columnspan=2, sticky="ew", pady=10)

        # Wyniki główne
        ttk.Label(result_frame, text="Poprawka [ppm]:", font=("TkDefaultFont", 10, "bold")).grid(row=4, column=0, sticky="w", pady=5)
        ttk.Label(result_frame, textvariable=self.res_ppm, foreground="blue", font=("TkDefaultFont", 10, "bold")).grid(row=4, column=1, sticky="e")

        ttk.Label(result_frame, text="Całkowita popr. ΔD [mm]:").grid(row=5, column=0, sticky="w", pady=5)
        ttk.Label(result_frame, textvariable=self.res_dd, font=("TkDefaultFont", 10, "bold")).grid(row=5, column=1, sticky="e")

        ttk.Label(result_frame, text="Długość popr. D [m]:", font=("TkDefaultFont", 11, "bold")).grid(row=6, column=0, sticky="w", pady=15)
        ttk.Label(result_frame, textvariable=self.res_final, foreground="green", font=("TkDefaultFont", 11, "bold")).grid(row=6, column=1, sticky="e")

    def _calculate_atmos_manual(self):
        try:
            lam = float(self.atm_lam_entry.get())
            ts = float(self.atm_ts_entry.get())
            tm = float(self.atm_tm_entry.get())
            p = float(self.atm_p_entry.get())
            d = float(self.atm_d_entry.get())
        except ValueError:
            messagebox.showerror("Błąd", "Wprowadź poprawne wartości liczbowe.")
            return

        res = calculations.calculate_atmospheric_correction_manual(lam, ts, tm, p, d)
        
        if res:
            self.res_ng0.set(f"{res['ng0']:.2f}")
            self.res_e.set(f"{res['e_hpa']:.2f}")
            self.res_ngr.set(f"{res['ngr']:.2f}")
            self.res_ppm.set(f"{res['ppm']:.2f}")
            self.res_dd.set(f"{res['delta_d_total_mm']:.2f}")
            self.res_final.set(f"{res['final_dist_m']:.4f}")

    # --- Zakładka 5: Przetwarzanie Wsadowe ---
    def _create_batch_tab(self):
        frame = self.tab5
        
        # --- Pasek sterowania (Góra) ---
        control_frame = ttk.LabelFrame(frame, text="Ustawienia i Import", padding=10)
        control_frame.pack(fill="x", pady=5)
        
        ttk.Label(control_frame, text="Długość fali λ [nm] (dla całej serii):").pack(side="left", padx=5)
        self.batch_lam_entry = ttk.Entry(control_frame, width=10, validate="key", validatecommand=self.vcmd)
        self.batch_lam_entry.insert(0, "850")
        self.batch_lam_entry.pack(side="left", padx=5)
        
        load_btn = ttk.Button(control_frame, text="Wczytaj plik i Oblicz", command=self._load_batch_file)
        load_btn.pack(side="left", padx=20)

        export_btn = ttk.Button(control_frame, text="Eksportuj Wyniki", command=self._export_batch_file)
        export_btn.pack(side="left", padx=5)

        # --- Tabela wyników (Środek) ---
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill="both", expand=True, pady=10)
        
        # Definicja kolumn
        cols = ("lp", "ts", "tm", "p", "d_zm", "ppm", "ng0", "d_pop")
        self.batch_tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        
        # Nagłówki
        self.batch_tree.heading("lp", text="Lp")
        self.batch_tree.heading("ts", text="Ts [°C]")
        self.batch_tree.heading("tm", text="Tm [°C]")
        self.batch_tree.heading("p", text="P [hPa]")
        self.batch_tree.heading("d_zm", text="D zmierz. [m]")
        self.batch_tree.heading("ppm", text="Popr. [ppm]")
        self.batch_tree.heading("ng0", text="Ng0")
        self.batch_tree.heading("d_pop", text="D popr. [m]")
        
        # Szerokości kolumn
        self.batch_tree.column("lp", width=40, anchor="center")
        self.batch_tree.column("ts", width=60, anchor="center")
        self.batch_tree.column("tm", width=60, anchor="center")
        self.batch_tree.column("p", width=70, anchor="center")
        self.batch_tree.column("d_zm", width=90, anchor="e")
        self.batch_tree.column("ppm", width=70, anchor="e")
        self.batch_tree.column("ng0", width=70, anchor="center")
        self.batch_tree.column("d_pop", width=100, anchor="e") # Wynik najważniejszy
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.batch_tree.yview)
        self.batch_tree.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        self.batch_tree.pack(side="left", fill="both", expand=True)

    def _load_batch_file(self):
        # 1. Pobierz Lambdę
        try:
            lam = float(self.batch_lam_entry.get())
        except ValueError:
            messagebox.showerror("Błąd", "Wprowadź poprawną długość fali λ przed wczytaniem pliku.")
            return

        # 2. Wybierz plik
        file_path = filedialog.askopenfilename(
            title="Wybierz plik z danymi (Lp; Ts; Tm; P; D)",
            filetypes=[("Pliki tekstowe/CSV", "*.txt;*.csv"), ("Wszystkie pliki", "*.*")]
        )
        if not file_path:
            return

        # 3. Przetwórz
        try:
            self.batch_data = calculations.process_batch_file(file_path, lam)
            
            if not self.batch_data:
                messagebox.showwarning("Pusty wynik", "Nie udało się wczytać poprawnych danych. Sprawdź format pliku.")
                return
            
            # 4. Wyświetl w tabeli
            # Najpierw czyścimy starą zawartość
            for row in self.batch_tree.get_children():
                self.batch_tree.delete(row)
                
            for row in self.batch_data:
                self.batch_tree.insert("", tk.END, values=(
                    row['lp'],
                    f"{row['ts']:.1f}",
                    f"{row['tm']:.1f}",
                    f"{row['p']:.1f}",
                    f"{row['d_zm']:.3f}",
                    f"{row['ppm']:.2f}",
                    f"{row['ng0']:.2f}",
                    f"{row['final_dist_m']:.4f}"
                ))
                
            messagebox.showinfo("Sukces", f"Przeliczono {len(self.batch_data)} rekordów.")
            
        except Exception as e:
            messagebox.showerror("Błąd przetwarzania", str(e))

    def _export_batch_file(self):
        if not self.batch_data:
            messagebox.showwarning("Brak danych", "Najpierw wczytaj i przelicz dane.")
            return
            
        file_path = filedialog.asksaveasfilename(
            title="Zapisz wyniki",
            defaultextension=".txt",
            filetypes=[("Plik tekstowy", "*.txt"), ("CSV", "*.csv")]
        )
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                # Nagłówek
                f.write("Lp;Ts;Tm;P;D_zm;PPM;Ng0;e_hpa;Ngr;D_popr\n")
                
                for row in self.batch_data:
                    line = (
                        f"{row['lp']};"
                        f"{row['ts']:.2f};"
                        f"{row['tm']:.2f};"
                        f"{row['p']:.2f};"
                        f"{row['d_zm']:.4f};"
                        f"{row['ppm']:.2f};"
                        f"{row['ng0']:.2f};"
                        f"{row['e_hpa']:.2f};"
                        f"{row['ngr']:.2f};"
                        f"{row['final_dist_m']:.5f}\n"
                    )
                    f.write(line)
            messagebox.showinfo("Sukces", "Plik został zapisany.")
        except Exception as e:
            messagebox.showerror("Błąd zapisu", str(e))

    # --- Zakładka 6: Geometria Ziemi (Łuk vs Cięciwa) ---
    def _create_geometry_tab(self):
        frame = self.tab6
        
        # Panel sterowania (Góra)
        control_frame = ttk.LabelFrame(frame, text="Zakres analizy", padding=10)
        control_frame.pack(fill="x", pady=5)
        
        ttk.Label(control_frame, text="Dystans start [km]:").pack(side="left", padx=5)
        self.geo_start_entry = ttk.Entry(control_frame, width=8, validate="key", validatecommand=self.vcmd)
        self.geo_start_entry.insert(0, "1")
        self.geo_start_entry.pack(side="left", padx=5)

        ttk.Label(control_frame, text="Dystans koniec [km]:").pack(side="left", padx=5)
        self.geo_end_entry = ttk.Entry(control_frame, width=8, validate="key", validatecommand=self.vcmd)
        self.geo_end_entry.insert(0, "100")
        self.geo_end_entry.pack(side="left", padx=5)

        ttk.Label(control_frame, text="Krok [km]:").pack(side="left", padx=5)
        self.geo_step_entry = ttk.Entry(control_frame, width=8, validate="key", validatecommand=self.vcmd)
        self.geo_step_entry.insert(0, "5")
        self.geo_step_entry.pack(side="left", padx=5)
        
        ttk.Button(control_frame, text="Analizuj Krzywiznę", command=self._generate_geometry_data).pack(side="left", padx=20)

        # Kontener na treść (Wykres + Tabela)
        content_frame = ttk.Frame(frame)
        content_frame.pack(fill="both", expand=True, pady=5)
        
        # 1. Tabela (Prawa strona)
        table_frame = ttk.Frame(content_frame, width=300)
        table_frame.pack(side="right", fill="y", padx=5)
        
        columns = ("dist", "diff")
        self.geo_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=15)
        self.geo_tree.heading("dist", text="Dystans [km]")
        self.geo_tree.heading("diff", text="Różnica s-c [mm]")
        self.geo_tree.column("dist", width=100, anchor="center")
        self.geo_tree.column("diff", width=120, anchor="center")
        
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.geo_tree.yview)
        self.geo_tree.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        self.geo_tree.pack(side="left", fill="both", expand=True)

        # 2. Wykres (Lewa strona)
        plot_frame = ttk.Frame(content_frame)
        plot_frame.pack(side="left", fill="both", expand=True)
        
        # Inicjalizacja figury Matplotlib
        self.geo_fig = Figure(figsize=(4, 4), dpi=100)
        self.geo_ax = self.geo_fig.add_subplot(111)
        
        self.geo_ax.set_title("Wpływ krzywizny Ziemi")
        self.geo_ax.set_xlabel("Odległość [km]")
        self.geo_ax.set_ylabel("Różnica (łuk - cięciwa) [mm]")
        self.geo_ax.grid(True)
        self.geo_fig.tight_layout()
        
        self.geo_canvas = FigureCanvasTkAgg(self.geo_fig, master=plot_frame)
        self.geo_canvas.draw()
        self.geo_canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

    def _generate_geometry_data(self):
        try:
            start = float(self.geo_start_entry.get())
            end = float(self.geo_end_entry.get())
            step = float(self.geo_step_entry.get())
        except ValueError:
            messagebox.showerror("Błąd", "Wprowadź poprawne wartości liczbowe.")
            return

        if start >= end:
             messagebox.showerror("Błąd", "Wartość początkowa musi być mniejsza od końcowej.")
             return
        if step <= 0:
             messagebox.showerror("Błąd", "Krok musi być dodatni.")
             return
        
        # Obliczenia
        data = calculations.calculate_arc_chord_difference_curve(start, end, step)
        
        # Aktualizacja tabeli
        for row in self.geo_tree.get_children():
            self.geo_tree.delete(row)
            
        x_vals = []
        y_vals = []
        
        for dist, diff in data:
            # Zmieniono formatowanie z .2f na .4f
            self.geo_tree.insert("", tk.END, values=(f"{dist:.1f}", f"{diff:.4f}"))
            x_vals.append(dist)
            y_vals.append(diff)
            
        # Aktualizacja wykresu
        self.geo_ax.clear()
        
        # Rysowanie linii i punktów
        self.geo_ax.plot(x_vals, y_vals, color='red', linewidth=2, label=r'$\Delta = \frac{s^3}{24R^2}$')
        
        self.geo_ax.set_title("Wpływ krzywizny Ziemi (Łuk - Cięciwa)")
        self.geo_ax.set_xlabel("Odległość [km]")
        self.geo_ax.set_ylabel("Różnica [mm]")
        self.geo_ax.legend()
        self.geo_ax.grid(True, linestyle='--', alpha=0.7)
        
        self.geo_fig.tight_layout()
        self.geo_canvas.draw()

    # --- Zakładka 7: Generator RAB-Code (Ulepszona) ---
    
    def _create_topcon_tab(self):
        frame = self.tab7
        
        # Ustawienia rysowania (zgodne z Twoim nowym kodem)
        self.tc_px_per_mm = 2  
        self.tc_bar_x_start = 20
        self.tc_bar_x_end = 150
        self.tc_label_x_pos = 170 
        self.tc_v_margin = 100
        
        # --- Góra: Sterowanie ---
        control_frame = ttk.LabelFrame(frame, text="Parametry i Eksport", padding=10)
        control_frame.pack(side="top", fill="x", pady=5)

        ttk.Label(control_frame, text="Wysokość start [mm]:").pack(side="left", padx=5)
        self.tc_start_entry = ttk.Entry(control_frame, width=10, validate="key", validatecommand=self.vcmd)
        self.tc_start_entry.insert(0, "0")
        self.tc_start_entry.pack(side="left", padx=5)

        ttk.Label(control_frame, text="Długość widoku [mm]:").pack(side="left", padx=5)
        self.tc_len_entry = ttk.Entry(control_frame, width=10, validate="key", validatecommand=self.vcmd)
        self.tc_len_entry.insert(0, "3000")
        self.tc_len_entry.pack(side="left", padx=5)

        # Przyciski
        gen_btn = tk.Button(control_frame, text="Generuj", command=self._generate_topcon, bg="#ffcc00", font=("TkDefaultFont", 9, "bold"))
        gen_btn.pack(side="left", padx=15)
        
        save_btn = tk.Button(control_frame, text="Zapisz jako PNG", command=self._save_topcon_image, bg="#4CAF50", fg="white", font=("TkDefaultFont", 9, "bold"))
        save_btn.pack(side="left", padx=5)

        # --- Środek: Kontener na Canvas i Tabelę ---
        content_frame = ttk.Frame(frame)
        content_frame.pack(side="top", fill="both", expand=True, pady=5)

        # Lewa strona: Wizualizacja (Canvas)
        canvas_container = ttk.LabelFrame(content_frame, text="Wizualizacja", padding=5)
        canvas_container.pack(side="left", fill="both", expand=True, padx=5)
        
        # Canvas z żółtym tłem
        self.tc_canvas = tk.Canvas(canvas_container, width=350, bg="#e1e81c", highlightthickness=0)
        v_scroll = ttk.Scrollbar(canvas_container, orient="vertical", command=self.tc_canvas.yview)
        self.tc_canvas.configure(yscrollcommand=v_scroll.set)
        
        v_scroll.pack(side="right", fill="y")
        self.tc_canvas.pack(side="left", fill="both", expand=True)

        # Prawa strona: Tabela danych
        table_container = ttk.LabelFrame(content_frame, text="Wykaz elementów", padding=5)
        table_container.pack(side="right", fill="both", expand=True, padx=5)

        columns = ("n", "typ", "os", "szer")
        self.tc_tree = ttk.Treeview(table_container, columns=columns, show="headings")
        
        self.tc_tree.heading("n", text="n")
        self.tc_tree.heading("typ", text="Typ")
        self.tc_tree.heading("os", text="Oś [mm]")
        self.tc_tree.heading("szer", text="Szer. [mm]")
        
        self.tc_tree.column("n", width=40, anchor="center")
        self.tc_tree.column("typ", width=50, anchor="center")
        self.tc_tree.column("os", width=80, anchor="e")
        self.tc_tree.column("szer", width=100, anchor="w")

        tree_scroll = ttk.Scrollbar(table_container, orient="vertical", command=self.tc_tree.yview)
        self.tc_tree.configure(yscrollcommand=tree_scroll.set)
        
        tree_scroll.pack(side="right", fill="y")
        self.tc_tree.pack(side="left", fill="both", expand=True)

        # Zmienne do przechowywania obiektu PIL (do zapisu)
        self.tc_pil_img = None
        self.tc_draw_pil = None
        self.tc_start_h = 0.0
        self.tc_view_len = 0.0

    # --- Metody pomocnicze (logika z latatapcon.py) ---

    def _topcon_get_y(self, pos_mm):
        """Przelicza mm na piksele (odwrócona oś Y - widok od dołu)."""
        dist_from_bottom_px = (pos_mm - self.tc_start_h) * self.tc_px_per_mm
        total_h_px = self.tc_view_len * self.tc_px_per_mm
        # Dodajemy margines, aby rysunek nie był przyklejony do krawędzi
        return (total_h_px - dist_from_bottom_px) + self.tc_v_margin

    def _topcon_draw_rect(self, y_center, h_px):
        """Rysuje prostokąt na Canvas i na obrazie PIL."""
        # Canvas Tkinter
        self.tc_canvas.create_rectangle(
            self.tc_bar_x_start, y_center - h_px/2, 
            self.tc_bar_x_end, y_center + h_px/2, 
            fill="black", outline="black"
        )
        # Obraz PIL (jeśli istnieje)
        if self.tc_draw_pil:
            self.tc_draw_pil.rectangle(
                [self.tc_bar_x_start, y_center - h_px/2, self.tc_bar_x_end, y_center + h_px/2], 
                fill="black"
            )

    def _topcon_draw_text(self, y, txt):
        """Rysuje tekst na Canvas i na obrazie PIL."""
        # Canvas Tkinter
        self.tc_canvas.create_text(
            self.tc_label_x_pos, y, 
            text=txt, anchor="w", font=("Arial", 8, "bold")
        )
        # Obraz PIL
        if self.tc_draw_pil:
            # Rysujemy tekst na PIL (może wymagać dopasowania pozycji Y względem fontu)
            self.tc_draw_pil.text((self.tc_label_x_pos, y - 5), txt, fill="black")

    def _generate_topcon(self):
        try:
            self.tc_start_h = float(self.tc_start_entry.get())
            self.tc_view_len = float(self.tc_len_entry.get())
        except ValueError:
            messagebox.showerror("Błąd", "Wprowadź poprawne wartości liczbowe.")
            return

        # 1. Pobierz dane matematyczne z calculations.py
        data = calculations.generate_topcon_rab_data(self.tc_start_h, self.tc_view_len)
        
        # 2. Przygotuj Canvas i PIL
        self.tc_canvas.delete("all")
        for item in self.tc_tree.get_children():
            self.tc_tree.delete(item)

        full_h_px = int(self.tc_view_len * self.tc_px_per_mm + 2 * self.tc_v_margin)
        self.tc_canvas.config(scrollregion=(0, 0, 350, full_h_px))
        
        # Inicjalizacja obrazu PIL (do zapisu)
        self.tc_pil_img = Image.new("RGB", (350, full_h_px), "#e1e81c")
        self.tc_draw_pil = ImageDraw.Draw(self.tc_pil_img)
        
        # 3. Pętla rysowania i wypełniania tabeli
        for item in data:
            n = item['n']
            pos_mm = item['pos_mm']
            typ = item['type']
            width_mm = item['width_mm']
            desc = item['desc']

            # Dodaj do tabeli
            self.tc_tree.insert("", tk.END, values=(n, typ, f"{pos_mm:.1f}", desc))

            # Rysowanie
            if typ == 'R':
                # Wzór R to 3 paski (przesunięcie -3, 0, +3 mm)
                for offset in [-3.0, 0.0, 3.0]:
                    y = self._topcon_get_y(pos_mm + offset)
                    h_px = 2.0 * self.tc_px_per_mm # Stała wysokość paska R = 2mm (na łacie)
                    self._topcon_draw_rect(y, h_px)
                
                # Etykieta tekstowa dla R
                y_text = self._topcon_get_y(pos_mm)
                self._topcon_draw_text(y_text, f"R({n}) {pos_mm:.0f}")
                
            else:
                # Typ A lub B (pojedynczy pasek o zmiennej szerokości)
                y = self._topcon_get_y(pos_mm)
                h_px = width_mm * self.tc_px_per_mm
                self._topcon_draw_rect(y, h_px)
                
                # Etykieta tekstowa
                self._topcon_draw_text(y, f"{typ}({n}) {pos_mm:.0f}")

        # Przewiń na dół (tam gdzie jest początek łaty w tym widoku)
        self.tc_canvas.yview_moveto(1.0)

    def _save_topcon_image(self):
        if self.tc_pil_img is None:
            messagebox.showwarning("Brak danych", "Najpierw wygeneruj widok łaty.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Zapisz obraz łaty",
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")]
        )
        if file_path:
            try:
                self.tc_pil_img.save(file_path)
                messagebox.showinfo("Sukces", "Obraz zapisany pomyślnie!")
            except Exception as e:
                messagebox.showerror("Błąd zapisu", str(e))
    
    def _create_serial_terminal_tab(self):
        frame = self.tab8
        
        # 1. Pasek narzędzi u góry zakładki
        toolbar = tk.Frame(frame, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        self.btn_serial_settings = ttk.Button(toolbar, text="Ustawienia", command=self._serial_open_settings)
        self.btn_serial_settings.pack(side=tk.LEFT, padx=2, pady=2)

        self.btn_serial_connect = ttk.Button(toolbar, text="Połącz", command=self._serial_toggle_connection)
        self.btn_serial_connect.pack(side=tk.LEFT, padx=2, pady=2)

        self.btn_serial_clear = ttk.Button(toolbar, text="Wyczyść", command=self._serial_clear_console)
        self.btn_serial_clear.pack(side=tk.LEFT, padx=2, pady=2)
        
        self.btn_serial_save = ttk.Button(toolbar, text="Zapisz do pliku", command=self._serial_save_to_file)
        self.btn_serial_save.pack(side=tk.LEFT, padx=2, pady=2)

        # Status połączenia
        self.serial_status_lbl = tk.Label(toolbar, text="Rozłączony", fg="red")
        self.serial_status_lbl.pack(side=tk.RIGHT, padx=10)

        # 2. Główne okno tekstowe (odbieranie danych)
        self.serial_console = scrolledtext.ScrolledText(frame, state='disabled', height=15)
        self.serial_console.pack(expand=True, fill='both', padx=5, pady=5)
        # Tagi kolorów
        self.serial_console.tag_config('sent', foreground='blue')
        self.serial_console.tag_config('received', foreground='green')

        # 3. Pole do wpisywania poleceń
        input_frame = tk.Frame(frame)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        tk.Label(input_frame, text="Wyślij:").pack(side=tk.LEFT)
        
        self.serial_entry_cmd = ttk.Entry(input_frame)
        self.serial_entry_cmd.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.serial_entry_cmd.bind('<Return>', lambda event: self._serial_send_data())

        btn_send = ttk.Button(input_frame, text="Wyślij", command=self._serial_send_data)
        btn_send.pack(side=tk.RIGHT)

        # --- Metody obsługi Terminala Szeregowego ---

    def _serial_open_settings(self):
        settings_win = tk.Toplevel(self)
        settings_win.title("Konfiguracja portu")
        settings_win.geometry("300x350")
        settings_win.grab_set()

        frame = ttk.LabelFrame(settings_win, text="Port configuration", padding=10)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        row = 0
        def create_row(label_text, variable, values):
            nonlocal row
            ttk.Label(frame, text=label_text).grid(column=0, row=row, sticky=tk.W, pady=5)
            combo = ttk.Combobox(frame, textvariable=variable, values=values, state="readonly")
            combo.grid(column=1, row=row, sticky=tk.E, pady=5)
            row += 1
            return combo

        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            ports = ["Brak portów"]
        
        if not self.serial_port_var.get() and ports:
            self.serial_port_var.set(ports[0])

        create_row("Port", self.serial_port_var, ports)
        create_row("Baud rate", self.serial_baud_var, [9600, 19200, 38400, 57600, 115200])
        create_row("Data bits", self.serial_databits_var, [5, 6, 7, 8])
        create_row("Stop bits", self.serial_stopbits_var, [1, 1.5, 2])
        create_row("Parity", self.serial_parity_var, ["None", "Even", "Odd", "Mark", "Space"])
        create_row("Flow control", self.serial_flow_var, ["None", "XON/XOFF", "RTS/CTS"])
        
        ttk.Label(frame, text="Forward").grid(column=0, row=row, sticky=tk.W, pady=5)
        ttk.Combobox(frame, values=["none"], state="disabled").grid(column=1, row=row, sticky=tk.E, pady=5)

        ttk.Button(settings_win, text="OK", command=settings_win.destroy).pack(pady=10)

    def _serial_get_parity_const(self):
        mapping = {
            "None": serial.PARITY_NONE,
            "Even": serial.PARITY_EVEN,
            "Odd": serial.PARITY_ODD,
            "Mark": serial.PARITY_MARK,
            "Space": serial.PARITY_SPACE
        }
        return mapping.get(self.serial_parity_var.get(), serial.PARITY_NONE)

    def _serial_get_flow_const(self):
        val = self.serial_flow_var.get()
        xon = False
        rts = False
        if val == "XON/XOFF":
            xon = True
        elif val == "RTS/CTS":
            rts = True
        return xon, rts

    def _serial_toggle_connection(self):
        if self.serial_is_connected:
            self._serial_disconnect()
        else:
            self._serial_connect()

    def _serial_connect(self):
        port = self.serial_port_var.get()
        if not port or port == "Brak portów":
            messagebox.showerror("Błąd", "Wybierz poprawny port COM.")
            return

        try:
            xon, rts = self._serial_get_flow_const()
            
            self.serial_conn = serial.Serial(
                port=port,
                baudrate=self.serial_baud_var.get(),
                bytesize=self.serial_databits_var.get(),
                stopbits=self.serial_stopbits_var.get(),
                parity=self._serial_get_parity_const(),
                xonxoff=xon,
                rtscts=rts,
                timeout=1,
                dsrdtr=True
            )
            
            time.sleep(1.0) # Stabilizacja połączenia
            
            self.serial_is_connected = True
            self.btn_serial_connect.config(text="Rozłącz")
            self.serial_status_lbl.config(text=f"Połączono: {port}", fg="green")
            self.btn_serial_settings.config(state="disabled")
            
            self.serial_read_thread = threading.Thread(target=self._serial_read_loop, daemon=True)
            self.serial_read_thread.start()
            
        except serial.SerialException as e:
            messagebox.showerror("Błąd połączenia", f"Nie udało się połączyć:\n{e}")

    def _serial_disconnect(self):
        self.serial_is_connected = False
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except:
                pass
        self.btn_serial_connect.config(text="Połącz")
        self.serial_status_lbl.config(text="Rozłączony", fg="red")
        self.btn_serial_settings.config(state="normal")

    def _serial_read_loop(self):
        while self.serial_is_connected and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    if data:
                        try:
                            decoded_data = data.decode('utf-8', errors='replace')
                        except:
                            decoded_data = str(data)
                        
                        self.after(0, self._serial_append_to_console, decoded_data, 'received')
                else:
                    time.sleep(0.01)

            except Exception as e:
                if self.serial_is_connected:
                    print(f"Błąd odczytu serial: {e}")
                    self.after(0, self._serial_disconnect)
                break

    def _serial_send_data(self):
        if not self.serial_is_connected:
            messagebox.showwarning("Uwaga", "Nie jesteś połączony z portem.")
            return

        cmd = self.serial_entry_cmd.get()
        if cmd:
            try:
                data_to_send = (cmd + "\r\n").encode('utf-8')
                self.serial_conn.write(data_to_send)
                self._serial_append_to_console(f"TX: {cmd}\n", 'sent')
                self.serial_entry_cmd.delete(0, tk.END)
            except Exception as e:
                messagebox.showerror("Błąd wysyłania", str(e))
                self._serial_disconnect()

    def _serial_append_to_console(self, text, tag):
        self.serial_console.config(state='normal')
        self.serial_console.insert(tk.END, text, tag)
        self.serial_console.see(tk.END)
        self.serial_console.config(state='disabled')

    def _serial_clear_console(self):
        self.serial_console.config(state='normal')
        self.serial_console.delete(1.0, tk.END)
        self.serial_console.config(state='disabled')

    def _serial_save_to_file(self):
        content = self.serial_console.get(1.0, tk.END)
        if not content.strip():
            messagebox.showinfo("Info", "Brak danych do zapisania.")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")]
        )
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("Sukces", "Logi terminala zapisane.")

# --- Uruchomienie aplikacji ---
if __name__ == "__main__":
    app = GeodeticApp()
    app.mainloop()