#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "time.h"

// --- Ρυθμίσεις Δικτύου & Server ---
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASS     = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL    = "http://192.168.1.100:8000/api/v1/telemetry"; // Βάλε την IP του υπολογιστή σου
const char* NODE_ID       = "ESP32-NODE-01";

// --- Δομή Πακέτου Τηλεμετρίας (Συμβατή με το Pydantic model του Server) ---
struct TelemetryPacket {
    uint32_t seq_num;
    double timestamp;
    float temp_c;
    float voltage_v;
    float lat;
    float lon;
    bool buffered;
};

// --- Υλοποίηση Στατικού Ring Buffer (Χωρίς Heap Fragmentation) ---
#define RING_BUFFER_SIZE 50      // Χωρητικότητα: 50 πακέτα εκτός δικτύου
#define MAX_BATCH_SIZE   10      // Μέγιστος αριθμός πακέτων ανά HTTP POST (για προστασία RAM)

class RingBuffer {
private:
    TelemetryPacket buffer[RING_BUFFER_SIZE];
    size_t head = 0;
    size_t tail = 0;
    size_t count = 0;

public:
    void push(TelemetryPacket pkt) {
        pkt.buffered = true;
        buffer[head] = pkt;
        head = (head + 1) % RING_BUFFER_SIZE;
        if (count == RING_BUFFER_SIZE) {
            // Αν γεμίσει η μνήμη, αντικαθιστά το πιο παλιό πακέτο (Overwrite oldest)
            tail = (tail + 1) % RING_BUFFER_SIZE;
        } else {
            count++;
        }
    }

    size_t size() const { return count; }

    // Διαβάζει πακέτο χωρίς να το διαγράψει ακόμα (μέχρι να επιβεβαιωθεί το HTTP 200 OK)
    TelemetryPacket peek(size_t index) const {
        size_t pos = (tail + index) % RING_BUFFER_SIZE;
        return buffer[pos];
    }

    // Διαγράφει τα πακέτα αφού σταλούν επιτυχώς στον Server
    void pop_batch(size_t num) {
        if (num > count) num = count;
        tail = (tail + num) % RING_BUFFER_SIZE;
        count -= num;
    }
};

RingBuffer offlineBuffer;
uint32_t sequenceNumber = 0;
unsigned long lastMeasureTime = 0;
const unsigned long INTERVAL_MS = 5000; // Μέτρηση κάθε 5 δευτερόλεπτα

// --- Ανάγνωση Αισθητήρων (Μπορείς να συνδέσεις DS18B20, GPS NEO-6M & Διαιρέτη Τάσης) ---
TelemetryPacket readSensors() {
    sequenceNumber++;
    
    // Λήψη πραγματικού Unix Timestamp (ή fallback σε millis αν δεν έχει συγχρονίσει NTP)
    time_t now;
    time(&now);
    double currentTimestamp = (now > 100000) ? (double)now : (millis() / 1000.0);

    // Εικονικές τιμές με μικρή διακύμανση (Έτοιμο για αντικατάσταση με analogRead / OneWire)
    float simulatedTemp = 3.8 + (random(-20, 25) / 100.0);
    float simulatedVolt = 12.4 + (random(-10, 10) / 100.0);

    return TelemetryPacket{
        sequenceNumber,
        currentTimestamp,
        simulatedTemp,
        simulatedVolt,
        38.2466, // Γεωγραφικό πλάτος
        21.7346, // Γεωγραφικό μήκος
        false
    };
}

// --- Αποστολή Πακέτων & Batch Sync ---
bool sendTelemetryWithSync(const TelemetryPacket& currentPkt) {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[OFFLINE] Απώλεια WiFi/4G! Αποθήκευση στο Ring Buffer...");
        offlineBuffer.push(currentPkt);
        return false;
    }

    HTTPClient http;
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(3000);

    // Δημιουργία JSON Payload: {"packets": [ ... ]}
    JsonDocument doc;
    JsonArray packetsArray = doc["packets"].to<JsonArray>();

    // 1. Προσθέτουμε πρώτα όσα πακέτα περιμένουν στο Ring Buffer (έως MAX_BATCH_SIZE)
    size_t bufferedToSend = min(offlineBuffer.size(), (size_t)MAX_BATCH_SIZE);
    for (size_t i = 0; i < bufferedToSend; i++) {
        TelemetryPacket bPkt = offlineBuffer.peek(i);
        JsonObject obj = packetsArray.add<JsonObject>();
        obj["node_id"]   = NODE_ID;
        obj["seq_num"]   = bPkt.seq_num;
        obj["timestamp"] = bPkt.timestamp;
        obj["temp_c"]    = bPkt.temp_c;
        obj["voltage_v"] = bPkt.voltage_v;
        obj["lat"]       = bPkt.lat;
        obj["lon"]       = bPkt.lon;
        obj["buffered"]  = true;
    }

    // 2. Προσθέτουμε το τρέχον (ζωντανό) πακέτο
    JsonObject currObj = packetsArray.add<JsonObject>();
    currObj["node_id"]   = NODE_ID;
    currObj["seq_num"]   = currentPkt.seq_num;
    currObj["timestamp"] = currentPkt.timestamp;
    currObj["temp_c"]    = currentPkt.temp_c;
    currObj["voltage_v"] = currentPkt.voltage_v;
    currObj["lat"]       = currentPkt.lat;
    currObj["lon"]       = currentPkt.lon;
    currObj["buffered"]  = false;

    String jsonPayload;
    serializeJson(doc, jsonPayload);

    int httpResponseCode = http.POST(jsonPayload);

    if (httpResponseCode == 200) {
        if (bufferedToSend > 0) {
            offlineBuffer.pop_batch(bufferedToSend);
            Serial.printf("[BATCH SYNC] Εστάλησαν %u αποθηκευμένα πακέτα + το τρέχον #%u (Υπόλοιπο Buffer: %u)\n",
                          bufferedToSend, currentPkt.seq_num, offlineBuffer.size());
        } else {
            Serial.printf("[ONLINE] Πακέτο #%u εστάλη επιτυχώς | Temp: %.2f C | Volt: %.2f V\n",
                          currentPkt.seq_num, currentPkt.temp_c, currentPkt.voltage_v);
        }
        http.end();
        return true;
    } else {
        Serial.printf("[HTTP ERROR %d] Ο Server δεν απάντησε. Αποθήκευση #%u στο Ring Buffer.\n",
                      httpResponseCode, currentPkt.seq_num);
        offlineBuffer.push(currentPkt);
        http.end();
        return false;
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n=== EdgePulse ESP32 Telemetry Node ===");

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("Σύνδεση στο WiFi");
    
    int retries = 0;
    while (WiFi.status() != WL_CONNECTED && retries < 15) {
        delay(500);
        Serial.print(".");
        retries++;
    }
    Serial.println();

    // Συγχρονισμός ώρας NTP για ακριβή Unix Timestamps
    if (WiFi.status() == WL_CONNECTED) {
        configTime(0, 0, "pool.ntp.org", "time.nist.gov");
        Serial.print("IP Κόμβου: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("Εκκίνηση σε Offline Mode (Τα πακέτα θα μπαίνουν στο Ring Buffer).");
    }
}

void loop() {
    if (millis() - lastMeasureTime >= INTERVAL_MS) {
        lastMeasureTime = millis();
        TelemetryPacket pkt = readSensors();
        sendTelemetryWithSync(pkt);
    }
}