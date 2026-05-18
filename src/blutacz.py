import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import datetime

class SerialTerminal:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Serial Terminal")
        self.root.geometry("600x500")

        # Zmienne konfiguracyjne (domyślne wartości)
        self.port_var = tk.StringVar()
        self.baud_var = tk.IntVar(value=57600)
        self.databits_var = tk.IntVar(value=8)
        self.stopbits_var = tk.DoubleVar(value=1)
        self.parity_var = tk.StringVar(value="None")
        self.flow_var = tk.StringVar(value="None")
        
        self.serial_conn = None
        self.is_connected = False
        self.read_thread = None

        # --- Budowa Interfejsu ---
        self.create_widgets()

    def create_widgets(self):
        # 1. Pasek narzędzi u góry
        toolbar = tk.Frame(self.root, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        self.btn_settings = ttk.Button(toolbar, text="Ustawienia", command=self.open_settings_window)
        self.btn_settings.pack(side=tk.LEFT, padx=2, pady=2)

        self.btn_connect = ttk.Button(toolbar, text="Połącz", command=self.toggle_connection)
        self.btn_connect.pack(side=tk.LEFT, padx=2, pady=2)

        self.btn_clear = ttk.Button(toolbar, text="Wyczyść", command=self.clear_console)
        self.btn_clear.pack(side=tk.LEFT, padx=2, pady=2)
        
        self.btn_save = ttk.Button(toolbar, text="Zapisz do pliku", command=self.save_to_file)
        self.btn_save.pack(side=tk.LEFT, padx=2, pady=2)

        # Status połączenia
        self.status_lbl = tk.Label(toolbar, text="Rozłączony", fg="red")
        self.status_lbl.pack(side=tk.RIGHT, padx=10)

        # 2. Główne okno tekstowe (odbieranie danych)
        self.console_text = scrolledtext.ScrolledText(self.root, state='disabled', height=15)
        self.console_text.pack(expand=True, fill='both', padx=5, pady=5)
        # Konfiguracja tagów kolorów dla tekstu wysyłanego i odbieranego
        self.console_text.tag_config('sent', foreground='blue')
        self.console_text.tag_config('received', foreground='green')

        # 3. Pole do wpisywania poleceń
        input_frame = tk.Frame(self.root)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        tk.Label(input_frame, text="Wyślij:").pack(side=tk.LEFT)
        
        self.entry_cmd = ttk.Entry(input_frame)
        self.entry_cmd.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.entry_cmd.bind('<Return>', lambda event: self.send_data()) # Wysyłanie Enterem

        btn_send = ttk.Button(input_frame, text="Wyślij", command=self.send_data)
        btn_send.pack(side=tk.RIGHT)

    def open_settings_window(self):
        """Otwiera okno dialogowe z ustawieniami wzorowane na zrzucie ekranu."""
        settings_win = tk.Toplevel(self.root)
        settings_win.title("Port configuration")
        settings_win.geometry("300x350")
        settings_win.grab_set() # Blokuje główne okno

        # Kontener
        frame = ttk.LabelFrame(settings_win, text="Port configuration", padding=10)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Helper do tworzenia rzędów
        row = 0
        def create_row(label_text, variable, values):
            nonlocal row
            ttk.Label(frame, text=label_text).grid(column=0, row=row, sticky=tk.W, pady=5)
            combo = ttk.Combobox(frame, textvariable=variable, values=values, state="readonly")
            combo.grid(column=1, row=row, sticky=tk.E, pady=5)
            row += 1
            return combo

        # Pobieranie listy dostępnych portów COM
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            ports = ["Brak portów"]
        
        # Jeśli port nie jest ustawiony, ustaw pierwszy z listy
        if not self.port_var.get() and ports:
            self.port_var.set(ports[0])

        # Tworzenie pól wyboru zgodnie ze zrzutem ekranu
        create_row("Port", self.port_var, ports)
        create_row("Baud rate", self.baud_var, [9600, 19200, 38400, 57600, 115200])
        create_row("Data bits", self.databits_var, [5, 6, 7, 8])
        create_row("Stop bits", self.stopbits_var, [1, 1.5, 2])
        create_row("Parity", self.parity_var, ["None", "Even", "Odd", "Mark", "Space"])
        create_row("Flow control", self.flow_var, ["None", "XON/XOFF", "RTS/CTS"])
        
        # Opcja Forward (tylko wizualnie, dla zgodności ze screenem - implementacja jest złożona)
        ttk.Label(frame, text="Forward").grid(column=0, row=row, sticky=tk.W, pady=5)
        ttk.Combobox(frame, values=["none"], state="disabled").grid(column=1, row=row, sticky=tk.E, pady=5)

        # Przycisk Zamknij
        ttk.Button(settings_win, text="OK", command=settings_win.destroy).pack(pady=10)

    def get_parity_const(self):
        mapping = {
            "None": serial.PARITY_NONE,
            "Even": serial.PARITY_EVEN,
            "Odd": serial.PARITY_ODD,
            "Mark": serial.PARITY_MARK,
            "Space": serial.PARITY_SPACE
        }
        return mapping.get(self.parity_var.get(), serial.PARITY_NONE)

    def get_flow_const(self):
        val = self.flow_var.get()
        xon = False
        rts = False
        if val == "XON/XOFF":
            xon = True
        elif val == "RTS/CTS":
            rts = True
        return xon, rts

    def toggle_connection(self):
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        port = self.port_var.get()
        if not port or port == "Brak portów":
            messagebox.showerror("Błąd", "Wybierz poprawny port COM.")
            return

        try:
            xon, rts = self.get_flow_const()
            
            self.serial_conn = serial.Serial(
                port=port,
                baudrate=self.baud_var.get(),
                bytesize=self.databits_var.get(),
                stopbits=self.stopbits_var.get(),
                parity=self.get_parity_const(),
                xonxoff=xon,
                rtscts=rts,
                timeout=1,        # Zwiększ timeout do 1 sekundy
                dsrdtr=True       # Czasami pomaga przy Bluetooth na Windows
            )
            self.is_connected = True
            self.btn_connect.config(text="Rozłącz")
            self.status_lbl.config(text=f"Połączono: {port} @ {self.baud_var.get()}", fg="green")
            self.btn_settings.config(state="disabled") # Blokada ustawień podczas połączenia
            
            # Uruchomienie wątku do czytania
            self.read_thread = threading.Thread(target=self.read_from_port, daemon=True)
            self.read_thread.start()
            
        except serial.SerialException as e:
            messagebox.showerror("Błąd połączenia", str(e))

    def disconnect(self):
        self.is_connected = False
        if self.serial_conn:
            self.serial_conn.close()
        self.btn_connect.config(text="Połącz")
        self.status_lbl.config(text="Rozłączony", fg="red")
        self.btn_settings.config(state="normal")

    def read_from_port(self):
        """Funkcja działająca w tle, nasłuchująca danych."""
        while self.is_connected and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    try:
                        decoded_data = data.decode('utf-8', errors='replace')
                    except:
                        decoded_data = str(data)
                    
                    # Aktualizacja GUI musi być bezpieczna wątkowo
                    self.root.after(0, self.append_to_console, decoded_data, 'received')
            except Exception as e:
                print(f"Błąd odczytu: {e}")
                break

    def send_data(self):
        if not self.is_connected:
            messagebox.showwarning("Uwaga", "Nie jesteś połączony z portem.")
            return

        cmd = self.entry_cmd.get()
        if cmd:
            try:
                # Dodajemy znak nowej linii (standard w terminalach)
                data_to_send = (cmd + "\r\n").encode('utf-8')
                self.serial_conn.write(data_to_send)
                self.append_to_console(f"TX: {cmd}\n", 'sent')
                self.entry_cmd.delete(0, tk.END)
            except Exception as e:
                messagebox.showerror("Błąd wysyłania", str(e))

    def append_to_console(self, text, tag):
        self.console_text.config(state='normal')
        self.console_text.insert(tk.END, text, tag)
        self.console_text.see(tk.END) # Autoscroll na dół
        self.console_text.config(state='disabled')

    def clear_console(self):
        self.console_text.config(state='normal')
        self.console_text.delete(1.0, tk.END)
        self.console_text.config(state='disabled')

    def save_to_file(self):
        content = self.console_text.get(1.0, tk.END)
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
            messagebox.showinfo("Sukces", "Dane zapisane pomyślnie.")

if __name__ == "__main__":
    root = tk.Tk()
    app = SerialTerminal(root)
    root.mainloop()