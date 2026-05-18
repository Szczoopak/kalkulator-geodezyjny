def validate_number_input(P):
    """
    Funkcja walidująca wprowadzane dane.
    - Zezwala na liczby dodatnie i ujemne.
    - Zezwala tylko na jedną kropkę dziesiętną.
    - Blokuje liczby typu '01' lub '-01' (dozwolone '0', '-0' lub '0.1').
    - Zezwala na stan przejściowy: sam '-', '1.', '-.', '-0.'.
    """
    
    if P == "" or P == "-":
        return True  # Zezwól na puste pole lub sam znak minus

    # Reguła: tylko jedna kropka dziesiętna i tylko jeden minus (na początku)
    if P.count('.') > 1 or P.count('-') > 1:
        return False
    
    if '-' in P and not P.startswith('-'):
        return False

    # Przygotuj "rdzeń" liczby do sprawdzenia zer wiodących (usuń minus jeśli istnieje)
    core = P[1:] if P.startswith('-') else P

    # Reguła: '0' nie może być pierwszą cyfrą, chyba że po nim jest kropka
    if core.startswith('0') and len(core) > 1 and core[1] != '.':
        return False

    # Spróbuj przekonwertować na float
    try:
        float(P)
        return True  # To jest poprawna liczba (dodatnia lub ujemna)
    except ValueError:
        # Obsługa stanów przejściowych (np. "123.", "-123.", "-.")
        if P.endswith('.'):
            # Usuwamy kropkę i ewentualny minus, reszta musi być cyframi lub pusta
            prefix = P[:-1]
            if prefix == "" or prefix == "-":
                return True # Zezwala na "." lub "-."
            
            # Sprawdź czy reszta przed kropką (po usunięciu minusa) to same cyfry
            if prefix.startswith('-'): prefix = prefix[1:]
            return prefix.isdigit()
        
        return False