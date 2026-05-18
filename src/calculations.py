import math

# --- Konwertery jednostek ---

def g2rad(grads):
    """Przelicza grady na radiany."""
    return grads * (math.pi / 200.0)

def g2cc(grads):
    """Przelicza grady na centycentygrady."""
    return grads * 10000.0

def cc2g(cc):
    """Przelicza centycentygrady na grady."""
    return cc / 10000.0

# --- Parsery plików ---

def parse_collimation_file(file_path):
    """Wczytuje pary odczytów (kolimacja) z pliku tekstowego."""
    readings = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                parts = line.strip().replace(',', '.').split()
                if len(parts) == 2:
                    try:
                        h1 = float(parts[0])
                        h2 = float(parts[1])
                        readings.append((h1, h2))
                    except ValueError:
                        pass  # Pomiń linie, które nie są parą liczb
    except Exception as e:
        # Zwróć błąd zamiast pustej listy, aby GUI mogło go wyświetlić
        raise IOError(f"Nie można otworzyć lub przetworzyć pliku: {e}")
    
    if not readings:
        raise ValueError("Nie znaleziono poprawnych odczytów w pliku.")
        
    return readings

def parse_inclination_file(file_path):
    """
    Wczytuje pełne dane inklinacji (c, mc, z, odczyty) z pliku.
    Oczekiwany format:
    c 5,5
    mc 0,9
    z 81,9768
    ...
    odczyt I   odczyt II
    60,2702  260,2679
    ...
    """
    data = {'c': None, 'mc': None, 'z': None, 'readings': []}
    
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line_cleaned = line.strip().replace(',', '.')
                parts = line_cleaned.split()
                
                if not parts:
                    continue  # Pomiń puste linie

                key = parts[0].lower()
                
                if key == 'c' and len(parts) == 2:
                    data['c'] = float(parts[1])
                elif key == 'mc' and len(parts) == 2:
                    data['mc'] = float(parts[1])
                elif key == 'z' and len(parts) == 2:
                    data['z'] = float(parts[1])
                else:
                    # Spróbuj sparsować jako odczyt
                    try:
                        h1 = float(parts[0])
                        h2 = float(parts[1])
                        data['readings'].append((h1, h2))
                    except (ValueError, IndexError):
                        # Pomiń linie, które nie są danymi
                        # (np. nagłówek "odczyt I odczyt II")
                        pass
                        
    except Exception as e:
        raise IOError(f"Nie można otworzyć lub przetworzyć pliku: {e}")

    # Walidacja wczytanych danych
    if data['c'] is None or data['mc'] is None or data['z'] is None:
        raise ValueError("Nie znaleziono w pliku kluczy 'c', 'mc' lub 'z'.")
    if not data['readings']:
        raise ValueError("Nie znaleziono poprawnych odczytów w pliku.")

    return data


# --- Funkcje obliczeniowe ---

def calculate_mean_collimation(readings):
    """
    Oblicza średnią kolimację i jej błąd na podstawie listy odczytów.
    'readings' to lista tupli, np. [(h1, h2), (h1, h2), ...] 
    """
    c_list_cc = []
    for h1, h2 in readings:
        c_g = (h2 - h1 - 200.0) / 2.0
        c_list_cc.append(g2cc(c_g))

    n = len(c_list_cc)
    if n < 2:
        return (c_list_cc[0], 0.0) if n == 1 else (0.0, 0.0)

    mean_c_cc = sum(c_list_cc) / n

    v_list = [c - mean_c_cc for c in c_list_cc]
    vv = sum([v**2 for v in v_list])
    mc_cc = math.sqrt(vv / (n * (n - 1)))

    return mean_c_cc, mc_cc

def calculate_mean_inclination(readings, c_cc, mc_cc, z_g):
    """
    Oblicza średnią inklinację i jej błąd.
    """
    d_prime_list_cc = []
    for h1, h2 in readings:
        d_prime_g = (h2 - h1 - 200.0) / 2.0
        d_prime_list_cc.append(g2cc(d_prime_g))

    n = len(d_prime_list_cc)
    if n < 2:
        return 0.0, 0.0 # Błąd
        
    mean_d_prime_cc = sum(d_prime_list_cc) / n
    
    v_list = [d - mean_d_prime_cc for d in d_prime_list_cc]
    vv = sum([v**2 for v in v_list])
    m_odcz_cc = math.sqrt(vv / (n * (n - 1))) 

    z_rad = g2rad(z_g)
    try:
        tan_z = math.tan(z_rad)
        cos_z = math.cos(z_rad)
        if cos_z == 0:
            return 0.0, 0.0 # Błąd, dzielenie przez zero (z=100g)
        sec_z = 1.0 / cos_z
    except ValueError:
        return 0.0, 0.0 # Błąd

    i_cc = (mean_d_prime_cc * tan_z) - (c_cc * sec_z)
    mi_cc = math.sqrt((tan_z**2 * m_odcz_cc**2) + (sec_z**2 * mc_cc**2))

    return i_cc, mi_cc

def calculate_corrected_reading(h_prime_g, z_prime_g, c_cc, i_cc):
    """
    Oblicza odczyt koła poziomego poprawiony o kolimację i inklinację.
    """
    c_g = cc2g(c_cc)
    i_g = cc2g(i_cc)
    z_rad = g2rad(z_prime_g)
    
    try:
        sin_z = math.sin(z_rad)
        tan_z = math.tan(z_rad)
        if sin_z == 0 or tan_z == 0:
            return h_prime_g 
        
        cosec_z = 1.0 / sin_z
        cotan_z = 1.0 / tan_z
    except ValueError:
        return h_prime_g

    delta_h_c_g = c_g * cosec_z
    delta_h_i_g = i_g * cotan_z
    
    h_corrected_g = h_prime_g + delta_h_c_g + delta_h_i_g
    
    return h_corrected_g

#Zakładka 3 - Współczynnik grupy Ng0

def calculate_ng0_curve(start_lambda_nm, end_lambda_nm, step_nm):
    """
    Generuje dane do wykresu i tabeli współczynnika grupy Ng0.
    Wzór Barrella i Searsa (grupa):
    Ng0 = A + B/(lambda^2) + C/(lambda^4)
    gdzie lambda w mikrometrach.
    """
    # Stałe dla wzoru grupowego (Barrell & Sears 1939)
    A = 287.6155
    B = 4.8866
    C = 0.0680
    
    results = []
    
    # Generowanie zakresu
    current_lambda = start_lambda_nm
    while current_lambda <= end_lambda_nm:
        lam_um = current_lambda / 1000.0  # konwersja nm -> um
        
        # Zabezpieczenie przed dzieleniem przez zero
        if lam_um == 0:
            current_lambda += step_nm
            continue
            
        term1 = B / (lam_um**2)
        term2 = C / (lam_um**4)
        
        ng0 = A + term1 + term2
        
        results.append((current_lambda, ng0))
        current_lambda += step_nm
        
    return results

# --- Zakładka 4: Poprawki Atmosferyczne ---

import math

def calculate_atmospheric_correction_manual(lam_nm, t_dry, t_wet, p_hpa, dist_m):
    """
    Optymalna funkcja obliczająca poprawkę atmosferyczną.
    Łączy precyzję wzorów IAG z czytelnym nazewnictwem.
    """
    # 1. Grupowy współczynnik załamania dla fali w próżni (Barrell & Sears)
    # n_g0 = A + B/λ² + C/λ⁴
    A, B, C = 287.604, 4.8864, 0.0680
    lam_um = lam_nm / 1000.0
    if lam_um == 0: return None
    
    ng0 = A + (B / (lam_um**2)) + (C / (lam_um**4))

    # 2. Obliczenie ciśnienia pary wodnej 'e' [hPa]
    # Ciśnienie nasycenia E_wet w temp. termometru mokrego
    E_wet = 6.112 * math.exp((17.67 * t_wet) / (t_wet + 243.5))
    
    # Rzeczywiste ciśnienie e (Wzór psychrometryczny Sprunga)
    psychro_const = 0.000662 
    e_hpa = E_wet - psychro_const * p_hpa * (t_dry - t_wet)
    if e_hpa < 0: e_hpa = 0

    # 3. Obliczenie współczynnika w warunkach rzeczywistych (ngr)
    # N = n_g0 * (273.15 / 1013.25) * (p / T) - (11.27 * e / T)
    T_kelvin = t_dry + 273.15
    ngr = (ng0 * (273.15 / 1013.25) * (p_hpa / T_kelvin)) - (11.27 * e_hpa / T_kelvin)

    # 4. Obliczenie współczynnika w warunkach standardowych instrumentu (ng_std)
    # Przyjmujemy standard geodezyjny: T=15C (288.15K), P=1013.25hPa, e=0 (powietrze suche)
    # Uwaga: Jeśli Twój instrument ma inny standard (np. e=10.87), należy to skorygować tutaj.
    T_std = 288.15
    p_std = 1013.25
    e_std = 0.0 # Standard dla większości nowoczesnych dalmierzy to 0% wilgotności
    ng_std = (ng0 * (273.15 / 1013.25) * (p_std / T_std)) - (11.27 * e_std / T_std)

    # 5. Obliczenie poprawki PPM (Różnica między standardem a rzeczywistością)
    ppm_val = ng_std - ngr
    
    # 6. Poprawka dystansu w mm i końcowy dystans w m
    delta_d_mm = (ppm_val * dist_m) / 1000.0
    final_dist = dist_m + (delta_d_mm / 1000.0)

    return {
        "ng0": round(ng0, 4),
        "e_hpa": round(e_hpa, 4),
        "ngr": round(ngr, 4),
        "ppm": round(ppm_val, 2),
        "delta_d_total_mm": round(delta_d_mm, 2),
        "final_dist_m": round(final_dist, 5)
    }

# --- Zakładka 5: Przetwarzanie Wsadowe ---

def process_batch_file(file_path, lam_nm):
    """
    Wczytuje plik (CSV/TXT), parsuje dane i wykonuje obliczenia dla każdego wiersza.
    Oczekiwany format: Lp; Ts; Tm; P; D_zm
    """
    processed_data = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.lower().startswith("lp"): 
                    continue # Pomiń puste linie i nagłówki
                
                # Obsługa separatorów (średnik lub tabulacja)
                if ";" in line:
                    parts = line.split(";")
                else:
                    parts = line.split() # Domyślnie białe znaki/tabulacja
                
                # Sprawdź czy mamy wystarczająco danych (Lp, Ts, Tm, P, D)
                if len(parts) >= 5:
                    try:
                        lp = parts[0].strip()
                        ts = float(parts[1].replace(',', '.'))
                        tm = float(parts[2].replace(',', '.'))
                        p = float(parts[3].replace(',', '.'))
                        d_zm = float(parts[4].replace(',', '.'))
                        
                        # Wykonaj obliczenie (używając funkcji z Zakładki 4)
                        res = calculate_atmospheric_correction_manual(lam_nm, ts, tm, p, d_zm)
                        
                        if res:
                            # Scalamy dane wejściowe z wynikami
                            entry = {
                                "lp": lp,
                                "ts": ts,
                                "tm": tm,
                                "p": p,
                                "d_zm": d_zm,
                                **res # Rozpakowanie wyników (ppm, ng0, final_dist itp.)
                            }
                            processed_data.append(entry)
                    except ValueError:
                        continue # Pomiń błędne wiersze
                        
    except Exception as e:
        raise IOError(f"Błąd odczytu pliku: {e}")
        
    return processed_data

# --- Zakładka 6: Geometria Ziemi (Łuk vs Cięciwa) ---

def calculate_arc_chord_difference_curve(start_km, end_km, step_km):
    """
    Generuje dane dotyczące różnicy między długością łuku (s) a cięciwą (c).
    Wzór przybliżony: delta = s^3 / (24 * R^2)
    R = 6378 km
    Wynik (delta) zwracany w mm.
    """
    R = 6378.0 * 8
    results = []
    
    current_dist = start_km
    # Zabezpieczenie przed pętlą nieskończoną
    if step_km <= 0:
        step_km = 1.0

    while current_dist <= end_km:
        # s = current_dist (zakładamy, że mierzona długość to długość łuku po powierzchni)
        # delta [km] = s^3 / (24 * R^2)
        
        delta_km = (current_dist**3) / (24 * (R**2))
        
        # Konwersja na mm: 1 km = 1,000,000 mm
        delta_mm = delta_km * 1000000.0
        
        results.append((current_dist, delta_mm))
        current_dist += step_km
        
    return results

# --- Zakładka 7: Generator RAB-Code (Topcon) ---

def _calculate_wa(n):
    """Oblicza szerokość elementu A dla indeksu n."""
    val = (2 * math.pi * (30.0 * n + 21.25)) / 330.0
    return 5.0 + 4.0 * math.cos(val)

def _calculate_wb(n):
    """Oblicza szerokość elementu B dla indeksu n."""
    val = (2 * math.pi * (30.0 * n + 35.0)) / 300.0
    return 5.0 + 4.0 * math.cos(val)

def generate_topcon_rab_data(start_mm, length_mm):
    """
    Generuje listę elementów łaty RAB w zadanym zakresie.
    Zwraca listę słowników: {'n', 'type', 'pos_mm', 'width_mm', 'desc'}
    """
    end_mm = start_mm + length_mm
    data = []

    # Zakres n (każdy cykl to 30mm)
    n_min = int(start_mm // 30)
    n_max = int(end_mm // 30) + 1

    for n in range(n_min, n_max):
        # --- Element R (Referencyjny - stały) ---
        # Pozycja: 30*n. Składa się z 3 pasków, ale w tabeli traktujemy jako jeden wpis.
        pos_r = 30.0 * n
        if start_mm <= pos_r <= end_mm:
            data.append({
                'n': n,
                'type': 'R',
                'pos_mm': pos_r,
                'width_mm': 8.0, # Całkowita szerokość wzoru
                'desc': 'Wzór stały'
            })

        # --- Element A (Zmienny) ---
        pos_a = 30.0 * n + 10.0
        if start_mm <= pos_a <= end_mm:
            width_a = _calculate_wa(n)
            data.append({
                'n': n,
                'type': 'A',
                'pos_mm': pos_a,
                'width_mm': width_a,
                'desc': f"{width_a:.3f}"
            })

        # --- Element B (Zmienny) ---
        pos_b = 30.0 * n + 20.0
        if start_mm <= pos_b <= end_mm:
            width_b = _calculate_wb(n)
            data.append({
                'n': n,
                'type': 'B',
                'pos_mm': pos_b,
                'width_mm': width_b,
                'desc': f"{width_b:.3f}"
            })
            
    return data