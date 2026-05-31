import requests
import pandas as pd
import datetime
import os
import random

# --- ΡΥΘΜΙΣΕΙΣ ΑΡΧΕΙΩΝ ---
EXCEL_FILE = "traffic_patra.xlsx"
CSV_FILE = "cloud_test_data.csv"

# --- ΑΣΦΑΛΗΣ ΦΟΡΤΩΣΗ ΚΛΕΙΔΙΩΝ (ΑΠΟ GITHUB SECRETS) ---
# Διαβάζει τα κλειδιά από το κρυφό "χρηματοκιβώτιο" του GitHub
keys_string = os.environ.get("TOMTOM_API_KEYS", "")
API_KEYS = [k.strip() for k in keys_string.split(",")] if keys_string else []

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
]

print("🚀 Το σύστημα καταγραφής Cloud ξεκίνησε (Μονός Κύκλος)!")

request_counter = 0 
current_time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
print(f"\n--- Νέος κύκλος μετρήσεων: {current_time_str} ---")

try:
    df1 = pd.read_excel(EXCEL_FILE, sheet_name='Φύλλο1')
except Exception as e:
    print(f"⚠️ Σφάλμα κατά την ανάγνωση του Excel: {e}")
    exit()
    
file_exists = os.path.isfile(CSV_FILE)
results = []

print(f"📡 Συλλογή Live δεδομένων για τις κύριες οδούς της Πάτρας...")
for index, row in df1.iterrows():
    road_name = str(row['Road_Segment'])
    
    start_parts = [x.strip() for x in str(row['Start']).split(',')]
    end_parts = [x.strip() for x in str(row['End']).split(',')]
    start_coords = f"{start_parts[0]},{start_parts[1]}"
    end_coords = f"{end_parts[0]},{end_parts[1]}"
    
    success = False
    attempts = 0
    
    while not success and attempts < 4:
        try:
            # 🛑 ΔΙΚΛΕΙΔΑ ΑΣΦΑΛΕΙΑΣ
            if not API_KEYS:
                 print("\n🚨 ΚΡΙΤΙΚΟ ΣΦΑΛΜΑ: Δεν βρέθηκαν API Keys στο περιβάλλον! Το σύστημα τερματίζεται.")
                 exit()
                 
            # Κυκλική εναλλαγή (Round-Robin)
            current_key = API_KEYS[request_counter % len(API_KEYS)]
            
            url = f"https://api.tomtom.com/routing/1/calculateRoute/{start_coords}:{end_coords}/json"
            params = {'key': current_key, 'traffic': 'true', 'routeType': 'fastest', 'travelMode': 'car'}
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            # 1. ΕΠΙΤΥΧΙΑ (200 OK)
            if response.status_code == 200:
                data = response.json()
                if 'routes' in data:
                    summary = data['routes'][0]['summary']
                    travel_time_sec = summary.get('travelTimeInSeconds', 0)
                    length_m = summary.get('lengthInMeters', 0)
                    delay_sec = summary.get('trafficDelayInSeconds', 0)
                    
                    if travel_time_sec > 0:
                        speed_kmh = (length_m / 1000) / (travel_time_sec / 3600)
                    else:
                        speed_kmh = 0
                        
                    results.append({
                        'Timestamp': current_time_str, 'Road_Segment': road_name,
                        'Speed_kmh': round(speed_kmh, 1), 'Travel_Time_sec': travel_time_sec,
                        'Traffic_Delay_sec': delay_sec, 'Length_meters': length_m
                    })
                    print(f"✅ {road_name} | {round(speed_kmh, 1)} km/h")
                    success = True
                    request_counter += 1

            # 2. ΚΑΜΕΝΟ ΚΛΕΙΔΙ (401, 403)
            elif response.status_code in [401, 403]:
                print(f"   [!] Προσοχή: Το TomTom απέρριψε το κλειδί (Code {response.status_code}).")
                if current_key in API_KEYS:
                    API_KEYS.remove(current_key)
                print(f"   🗑️ Το κλειδί {current_key[:6]}... πετάχτηκε στα σκουπίδια!")
                attempts += 1

            # 3. RATE LIMIT (429)
            elif response.status_code == 429:
                print(f"   ⚠️ Φάγαμε Rate Limit (Code 429) στο κλειδί {current_key[:6]}... Δοκιμή με το επόμενο.")
                request_counter += 1
                attempts += 1
                
            # 4. ΑΛΛΟ ΑΓΝΩΣΤΟ ΣΦΑΛΜΑ
            else:
                print(f"   [!] Προσπάθεια {attempts+1}: Το TomTom απάντησε με άγνωστο Code {response.status_code}")
                request_counter += 1
                attempts += 1
                
        except Exception as e:
            print(f"   [!] Προσπάθεια {attempts+1}: Σφάλμα σύνδεσης -> {e}")
            request_counter += 1
            attempts += 1
            
    if not success:
        print(f"🚨 ΑΠΟΤΥΧΙΑ στο {road_name} - Όλες οι προσπάθειες απέτυχαν.")

if results:
    results_df = pd.DataFrame(results)
    results_df.to_csv(CSV_FILE, mode='a', header=not file_exists, index=False, sep=';')
    print(f"\n💾 Ο κύκλος ολοκληρώθηκε. Σώθηκαν {len(results)} LIVE εγγραφές στο {CSV_FILE}.")
    print("Τέλος διεργασίας Cloud.")
