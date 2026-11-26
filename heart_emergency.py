import pyautogui
import time
import requests
from geopy.geocoders import Nominatim
import threading

# CONFIG (इन्हें बदल सकते हो)
TRUSTED_CONTACTS = ["Mummy", "Jaan", "Bestie"]  # WhatsApp पर सेव नाम

SEARCH_BAR_X = 203
SEARCH_BAR_Y = 140

ATTACHMENT_PLUS_X = 950
ATTACHMENT_PLUS_Y = 1050

DOCUMENT_OPTION_X = 950
DOCUMENT_OPTION_Y = 820

UPDATE_INTERVAL = 60  # सेकंड में (हर 1 मिनट अपडेट)

# ग्लोबल फ्लैग
emergency_active = False

# ────────────────────────────────────────────────
# Heart की लाइव लोकेशन प्राप्त करने का फंक्शन
# ────────────────────────────────────────────────
def get_heart_live_location():
    try:
        # ipinfo.io से लोकेशन (फ्री और रिलायबल)
        response = requests.get('https://ipinfo.io/json', timeout=6)
        data = response.json()

        city = data.get('city', 'Unknown')
        region = data.get('region', 'Unknown')
        country = data.get('country', 'Unknown')
        loc = data.get('loc', 'Unknown')  # "lat,long"

        address = "पता नहीं मिला"
        if loc != 'Unknown':
            try:
                lat, lon = loc.split(',')
                geolocator = Nominatim(user_agent="heart-emergency")
                location = geolocator.reverse((lat, lon), timeout=8)
                if location and location.address:
                    address = location.address
            except:
                pass

        timestamp = time.strftime("%I:%M %p")

        return (
            f"📍 Heart की लाइव लोकेशन ({timestamp}):\n"
            f"{address}\n"
            f"{city}, {region}, {country}\n"
            f"Lat/Long: {loc}"
        )
    except Exception as e:
        return f"लोकेशन नहीं मिल पाई ({time.strftime('%I:%M %p')}) - {str(e)[:50]}"


# ────────────────────────────────────────────────
# WhatsApp में सर्च बार फोकस + मैसेज भेजने का फंक्शन
# ────────────────────────────────────────────────
def send_via_whatsapp(contact, message):
    try:
        # WhatsApp फोकस
        pyautogui.hotkey('win', 's')
        time.sleep(0.7)
        pyautogui.write('whatsapp')
        time.sleep(0.7)
        pyautogui.press('enter')
        time.sleep(5.5)

        # सर्च बार फोकस (Ctrl+F + क्लिक)
        pyautogui.hotkey('ctrl', 'f')
        time.sleep(1.0)
        pyautogui.click(x=SEARCH_BAR_X, y=SEARCH_BAR_Y)
        time.sleep(0.8)

        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('backspace')
        time.sleep(0.4)

        pyautogui.write(contact)
        time.sleep(2.0)
        pyautogui.press('down')
        pyautogui.press('enter')
        time.sleep(3.5)

        pyautogui.write(message)
        time.sleep(0.8)
        pyautogui.press('enter')
        time.sleep(1.5)

        return True
    except Exception as e:
        print(f"{contact} को मैसेज नहीं भेज पाया: {e}")
        return False


# ────────────────────────────────────────────────
# मुख्य इमरजेंसी फंक्शन – लाइव लोकेशन भेजता रहेगा
# ────────────────────────────────────────────────
def start_heart_emergency():
    global emergency_active

    if emergency_active:
        print("पहले से इमरजेंसी चल रही है")
        return

    emergency_active = True
    print("🚨 Heart Emergency शुरू – लाइव लोकेशन भेज रहा हूँ 🚨")

    # पहला मैसेज
    first_message = (
        "🚨 HEART EMERGENCY START 🚨\n"
        "मैं खतरे में हूँ – हर मिनट अपनी लोकेशन भेज रहा हूँ\n"
        "प्लीज मदद करें ❤️ – Heart"
    )
    for contact in TRUSTED_CONTACTS:
        send_via_whatsapp(contact, first_message)

    # लूप: हर INTERVAL सेकंड में अपडेट
    while emergency_active:
        location_text = get_heart_live_location()
        update_message = (
            "🔴 HEART LIVE LOCATION UPDATE\n"
            f"{location_text}\n"
            "मैं अभी भी खतरे में हूँ – मदद चाहिए\n"
            "प्लीज जल्दी करें ❤️"
        )

        for contact in TRUSTED_CONTACTS:
            send_via_whatsapp(contact, update_message)

        print("लाइव अपडेट भेजा गया")

        # समय बीतने का इंतजार
        for _ in range(UPDATE_INTERVAL):
            if not emergency_active:
                break
            time.sleep(1)

    print("इमरजेंसी मोड बंद हो गया")


# ────────────────────────────────────────────────
# इमरजेंसी रोकने का फंक्शन
# ────────────────────────────────────────────────
def stop_heart_emergency():
    global emergency_active
    emergency_active = False
    print("इमरजेंसी मोड बंद कर दिया गया")


# ────────────────────────────────────────────────
# इसे कैसे इस्तेमाल करो (उदाहरण)
# ────────────────────────────────────────────────
if __name__ == "__main__":
    print("Heart Emergency System तैयार है")
    print("ट्रिगर करने के लिए: start_heart_emergency() कॉल करें")
    print("रोकने के लिए: stop_heart_emergency() कॉल करें")

    # टेस्ट के लिए (अनकमेंट करके चलाओ)
    # start_heart_emergency()

    # या हॉटकी/वॉइस से ट्रिगर करो (अलग से जोड़ सकते हो)
